"""Shared response envelope.

Successful responses:  {"success": true, "data": <payload>}
Error responses:       {"success": false, "error": {"code", "message"}}
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT | None = None


def ok(data: DataT) -> ApiResponse[DataT]:
    return ApiResponse[DataT](success=True, data=data)
