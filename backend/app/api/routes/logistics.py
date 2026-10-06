from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.core.response import fail, ok
from app.service import logistics as logistics_service

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/logistics/by-order-no/{orderNo}")
def logistics_by_order_no(orderNo: str, includeEta: bool = True):
    data = logistics_service.get_by_order_no(orderNo, include_eta=includeEta)
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)


@router.get("/logistics/tracking")
def logistics_tracking(
    trackingNo: str,
    expressCompanyCode: Optional[str] = None,
    includeEta: bool = True,
):
    data = logistics_service.get_by_tracking(
        trackingNo,
        express_company_code=expressCompanyCode,
        include_eta=includeEta,
    )
    if "error" in data:
        err = data["error"]
        return fail(err["code"], err["message"])
    return ok(data)
