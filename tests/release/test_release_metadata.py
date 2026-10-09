"""Prevent beta, PR and topic-branch builds from replacing stable images."""
from pathlib import Path
import runpy
import unittest

metadata = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/release_metadata.py"))["release_metadata"]


class ReleaseChannels(unittest.TestCase):
    def test_stable_branch_publishes_latest(self):
        self.assertEqual(metadata("1.0.0", "push", "refs/heads/main"),
                         {"version": "1.0.0", "publish": "true", "moving_tag": "latest"})

    def test_beta_branch_only_publishes_beta(self):
        self.assertEqual(metadata("1.0.1-beta.1", "push", "refs/heads/beta"),
                         {"version": "1.0.1-beta.1", "publish": "true", "moving_tag": "beta"})

    def test_versions_cannot_cross_channels(self):
        for version, branch in [("1.0.0", "beta"), ("1.0.1-beta.1", "main")]:
            for event in ["push", "workflow_dispatch", "pull_request"]:
                with self.subTest(version=version, event=event), self.assertRaises(ValueError):
                    metadata(version, event, "refs/heads/" + branch, branch)

    def test_pull_requests_never_publish(self):
        for version, base in [("1.0.0", "main"), ("1.0.1-beta.1", "beta")]:
            result = metadata(version, "pull_request", "refs/pull/17/merge", base)
            self.assertEqual((result["publish"], result["moving_tag"]), ("false", ""))

    def test_topic_branches_never_publish(self):
        for event in ["push", "workflow_dispatch", "pull_request_target"]:
            result = metadata("1.0.0", event, "refs/heads/feature/test")
            self.assertEqual((result["publish"], result["moving_tag"]), ("false", ""))

    def test_manual_channel_builds(self):
        for version, branch, tag in [("1.0.0", "main", "latest"), ("1.0.1-beta.2", "beta", "beta")]:
            result = metadata(version, "workflow_dispatch", "refs/heads/" + branch)
            self.assertEqual((result["publish"], result["moving_tag"]), ("true", tag))

    def test_tags_publish_numbered_image_without_moving_channels(self):
        for version in ["1.0.0", "1.0.1-beta.1"]:
            result = metadata(version, "push", "refs/tags/v" + version)
            self.assertEqual((result["publish"], result["moving_tag"]), ("true", ""))
        with self.assertRaises(ValueError):
            metadata("1.0.0", "push", "refs/tags/v0.8.6")

    def test_invalid_versions_fail_closed(self):
        for version in ["latest", "1.0", "v1.0.0", "01.0.0", "1.0.0-beta", "1.0.0-beta.0", "1.0.0-beta.01", "1.0.0-rc.1", "1.0.0\nlatest"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                metadata(version, "push", "refs/heads/main")


if __name__ == "__main__":
    unittest.main()
