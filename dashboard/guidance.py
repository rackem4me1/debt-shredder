"""Plain-language help and synthetic practice inputs, not contract defaults."""
HELP = {
    'cash': 'Money already cleared in this account at the start. Do not include pending deposits.',
    'floor': 'A cushion you want left untouched. This is separate from reserved cash below.',
    'reserved': 'Money already set aside for another purpose in this same account. Enter 0 only if none is reserved.',
    'balance': 'The amount already posted to the card at the start. Keep interest not yet posted in the next field.',
    'unposted_interest': 'Interest accrued through the day before the forecast starts, but not yet on a statement. Do not assume 0 if it is unknown.',
    'apr_percent': 'Enter a percentage, such as 24.99, not 0.2499. Use the rate for this ordinary balance.',
    'start': 'The opening day for these balances. It must be after the previous statement close.',
    'end': 'The last day to calculate. This first form stops before the next statement closes.',
    'minimum_original': 'The minimum shown on the previous statement before any payments toward it.',
    'minimum_remaining': 'The portion of that minimum still unpaid at the start. It may be smaller than the original.',
    'payment_amount': 'A proposed payment, not a command to your bank. The app may limit it to protect cash.',
    'initiated': 'The day you would submit the payment. Cash is committed from this day.',
    'credited': 'The day the card company would apply it. This affects interest and the due-date check.',
    'debited': 'The day the money would leave checking. This form requires it to be on or after credit.',
    'settled': 'The day the payment would finish settling. Do not assume all four dates are the same.',
    'timezone': 'Use a named time zone such as America/Chicago; it determines which calendar day is used.',
}


def practice_inputs():
    return dict(name='Practice example', cash='150', floor='20', reserved='10', balance='500',
        unposted_interest='0', apr_percent='36.5', day_count='actual_365_fixed',
        start='2026-01-01', end='2026-01-21', previous_start='2025-12-01', previous_close='2025-12-31',
        minimum_due='2026-01-20', next_close='2026-01-31', next_due='2026-02-20',
        minimum_original='50', minimum_remaining='50', payment_amount='200', payment_kind='minimum',
        initiated='2026-01-02', credited='2026-01-03', debited='2026-01-04', settled='2026-01-05',
        timezone='America/Chicago')
