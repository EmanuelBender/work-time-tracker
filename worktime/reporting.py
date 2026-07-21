"""Report output shared by the GUI export and tests — no GUI dependencies."""

REPORT_CSV_HEADER = [
    "Project", "Employer", "Tracked Hours", "Billable Hours",
    "Rate", "Amount", "Currency",
]


def report_csv_rows(rows):
    """Yield CSV rows (header first) from db.totals_between() project rows."""
    yield REPORT_CSV_HEADER
    for row in rows:
        yield [
            row["project_name"],
            row["employer"],
            f"{row['tracked_hours']:.2f}",
            f"{row['billable_hours']:.2f}",
            f"{row['rate']:g}" if row["rate"] else "",
            f"{row['amount']:.2f}" if row["amount"] is not None else "",
            row["currency"],
        ]
