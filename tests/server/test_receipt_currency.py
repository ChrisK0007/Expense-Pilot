"""Currency evidence policy, without a model or external service."""
import unittest
from receipt_core import currency_fields

class CurrencyTest(unittest.TestCase):
    def test_unqualified_dollars_do_not_become_usd(self):
        for text in ['Total $25.00','GST $2.27 Total $25.00','Customer: Australia Total $25.00','']:
            d=currency_fields({'currency':'USD'},text)
            self.assertEqual(d['currency'],'AUD');self.assertEqual(d['currency_status'],'default')
    def test_printed_currency_overrides_model_guess(self):
        for text,code in [('Amount paid AUD 25.00','AUD'),('Total A$25.00','AUD'),('Total US$25.00','USD'),('Amount paid EUR 20.00','EUR'),('Total NZ$25.00','NZD')]:
            self.assertEqual(currency_fields({'currency':'USD','currency_evidence':'USD'},text)['currency'],code)
    def test_australian_details_are_only_a_suggestion(self):
        for text in ['Seller ABN 12 345 678 901 Total $25.00','example.com.au GST 2.27 Total $25.00']:
            d=currency_fields({'currency':'USD'},text)
            self.assertEqual(d['currency'],'AUD');self.assertEqual(d['currency_status'],'inferred')
        self.assertEqual(currency_fields({'currency':'AUD'},'ABN 12 345 678 901 Total USD 25.00')['currency'],'USD')
    def test_multiple_currency_and_visual_evidence(self):
        self.assertEqual(currency_fields({'currency':'USD'},'Paid AUD 40 equivalent USD 25')['currency'],'')
        self.assertEqual(currency_fields({'currency':'USD','currency_evidence':'$25.00'})['currency'],'AUD')
        self.assertEqual(currency_fields({'currency':'AUD','currency_evidence':'Total AUD 25.00'})['currency'],'AUD')
        # An ungrounded model quote cannot override independently extracted PDF text.
        self.assertEqual(currency_fields({'currency':'USD','currency_evidence':'USD'},'Example receipt. Total $25.00. Thank you.')['currency'],'AUD')
