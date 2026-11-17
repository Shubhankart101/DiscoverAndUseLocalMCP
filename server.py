from __future__ import annotations

import json

from fastmcp import FastMCP


server = FastMCP("Local Equipment Server")
CATALOGUE = {
    "drill-01": {"name": "Cordless Drill", "available": True},
    "meter-02": {"name": "Digital Multimeter", "available": False},
}


@server.resource("equipment://catalog")
def equipment_catalog() -> str:
    return json.dumps(CATALOGUE, sort_keys=True)


@server.tool()
def check_availability(equipment_id: str) -> dict:
    item = CATALOGUE.get(equipment_id)
    if item is None:
        return {"found": False, "equipment_id": equipment_id}
    return {"found": True, "equipment_id": equipment_id, "available": item["available"]}


@server.prompt()
def maintenance_prompt(equipment_id: str) -> str:
    return f"Prepare a maintenance request for {equipment_id}."


if __name__ == "__main__":
    server.run(transport="stdio")
