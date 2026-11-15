"""Advance the invoice sequence past previously issued numeric numbers."""
import json
from billing_numbers import sequence_number


def upgrade(connection):
    candidates = []
    for number, snapshot in connection.execute("""
        SELECT number,business FROM billing_documents WHERE kind='invoice' AND state<>'draft'
    """):
        prefix = json.loads(snapshot).get('invoice_prefix', 'INV-')
        candidates.append(sequence_number(number, prefix, legacy=True))
    for number, in connection.execute('SELECT number FROM billing_reusable_invoice_numbers'):
        candidates.append(sequence_number(number, 'INV-', legacy=True))
    highest = max((n for n in candidates if n is not None), default=0)
    connection.execute("UPDATE billing_counters SET next_number=MAX(next_number,?) WHERE kind='invoice'", (highest + 1,))
