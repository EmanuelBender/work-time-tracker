"""Report output shared by the GUI export and tests — no GUI dependencies."""

REPORT_CSV_HEADER = [
    "Project", "Employer", "Tracked Hours", "Billable Hours",
    "Fee EUR", "Effective EUR/h",
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
            f"{row['fee']:g}" if row["fee"] else "",
            f"{row['eff_rate']:.2f}" if row["eff_rate"] else "",
        ]
