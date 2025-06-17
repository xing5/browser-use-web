from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import uvicorn
import asyncio
import inspect
import re
import json

from browser_use.browser import BrowserSession, BrowserProfile
from src.controller.custom_controller import CustomController

# Singleton browser session (assume localhost:9222, Chromium CDP)
browser_session = None
controller = None

app = FastAPI()


class ActionRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}


@app.on_event("startup")
async def startup_event():
    global browser_session, controller
    browser_session = BrowserSession(
        cdp_url="http://localhost:9222",
        browser_profile=BrowserProfile(
            no_viewport=False,
            viewport={"width": 1920, "height": 990},
            highlight_elements=True,
        ),
    )
    controller = CustomController()


# Parse the selector string into a flat list
def _parse_selector_list(selector_str):
    lines = selector_str.splitlines()
    result = []
    interactive_tags = {
        "a",
        "button",
        "input",
        "textarea",
        "select",
        "option",
        "label",
    }
    for line in lines:
        content = line.lstrip("\t")
        m = re.match(r"\[(\d+)\]<([\w-]+)(.*?)>(.*)", content)
        if m:
            index = int(m.group(1))
            tag = m.group(2)
            attrs = m.group(3).strip()
            text = m.group(4).strip()
            # Only include if tag is interactive or has non-empty text
            if tag in interactive_tags or (text and text != "/"):
                node = {"index": index, "tag": tag}
                if attrs and attrs != "/":
                    node["attrs"] = attrs
                if text and text != "/":
                    node["text"] = text
                result.append(node)
    return result


def get_selector_list(selector_map):
    useful_attrs = {
        "id",
        "name",
        "type",
        "value",
        "href",
        "src",
        "alt",
        "title",
        "placeholder",
        "role",
        "class",
    }

    # Also include any attribute that starts with "aria-"
    def filter_attrs(attrs):
        return {
            k: v for k, v in attrs.items() if k in useful_attrs or k.startswith("aria-")
        }

    return [
        {
            "index": index,
            "tag": node.tag_name,
            "attrs": filter_attrs(node.attributes),
            "text": node.get_all_text_till_next_clickable_element(),
        }
        for index, node in selector_map.items()
    ]


async def _get_current_page():
    if not browser_session:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    # Wait for the page to load
    page = await browser_session.get_current_page()
    await page.wait_for_load_state("domcontentloaded", timeout=8000)
    await browser_session.get_state_summary(cache_clickable_elements_hashes=True)
    selector_map = await browser_session.get_selector_map()
    return get_selector_list(selector_map)


@app.post("/browser/action")
async def browser_action(request: ActionRequest):
    if not browser_session or not controller:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    try:
        # Delegate action execution to the controller's registry
        result = await controller.registry.execute_action(
            action_name=request.action,
            params=request.params,
            browser_session=browser_session,
        )
        content = await _get_current_page()
        return {"result": result, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/browser/status")
async def browser_status():
    if not browser_session:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    # Minimal status: list of open tabs and current URL
    try:
        tabs = browser_session.tabs
        current_tab = await browser_session.get_current_page()
        return {
            "num_tabs": len(tabs),
            "current_url": current_tab.url if current_tab else None,
            "tab_urls": [tab.url for tab in tabs],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/browser/selectors")
async def get_current_page():
    if not browser_session:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    return {"content": await _get_current_page()}


@app.get("/browser/content")
async def get_current_page_content():
    if not browser_session:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    return {"content": await browser_session.get_page_html()}


@app.get("/browser/actions")
async def list_browser_actions():
    if not controller:
        raise HTTPException(status_code=503, detail="Controller not initialized.")
    actions = controller.registry.registry.actions
    return [
        {"name": action.name, "description": action.description}
        for action in actions.values()
    ]


@app.get("/browser/element_html")
async def get_element_html(selector: str):
    if not browser_session:
        raise HTTPException(status_code=503, detail="Browser not connected.")
    try:
        page = await browser_session.get_current_page()
        locator = await page.locator(selector).all()
        html = [await el.evaluate("el => el.outerHTML") for el in locator]
    except Exception as e:
        print(e)
        return {"html": []}
    return {"html": html}


if __name__ == "__main__":
    uvicorn.run("browser_api:app", host="0.0.0.0", port=8000, reload=True)
