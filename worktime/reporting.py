"""Report output shared by the GUI export and tests — no GUI dependencies."""

AUTO_CONFIDENCES = ("auto-file", "auto-rule", "auto-title")


def coverage_line(summary):
    """One-line attribution health from db.totals_between(): how much tracked
    time attributed itself vs. needed the user. The gauge that tells us where
    detection accuracy work should go next."""
    total = summary["tracked_seconds"]
    if not total:
        return ""
    cs = summary["confidence_seconds"]

    def pct(seconds):
        return f"{round(100 * seconds / total)}%"

    auto = sum(cs.get(c, 0.0) for c in AUTO_CONFIDENCES)
    return (f"attribution   {pct(auto)} auto · {pct(cs.get('manual', 0.0))} you · "
            f"{pct(cs.get('inferred', 0.0))} guessed · {pct(cs.get('unassigned', 0.0))} unknown")


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
