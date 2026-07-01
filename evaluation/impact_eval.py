from __future__ import annotations

from domain.res import ImpactReport


def impact_smoke_check(report: ImpactReport) -> bool:
    return bool(report.direct_impacts or report.indirect_impacts)

