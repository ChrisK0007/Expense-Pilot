"""Close existing client links for quotes that have already been converted."""


def upgrade(connection):
    connection.execute("""
        UPDATE billing_quote_acceptance AS link
        SET token_hash=NULL
        WHERE token_hash IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM billing_documents doc
            WHERE doc.id=link.document_id AND doc.kind='quote'
              AND (
                doc.state='converted'
                OR (doc.state='accepted' AND EXISTS (
                    SELECT 1 FROM audit converted
                    WHERE converted.entity=CAST(doc.id AS TEXT)
                      AND converted.action='document convert'
                      AND converted.id > (
                        SELECT MAX(created.id) FROM audit created
                        WHERE created.entity=CAST(doc.id AS TEXT)
                          AND created.action='quote draft created'
                      )
                ))
              )
          )
    """)
