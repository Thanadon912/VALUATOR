#!/usr/bin/env python3
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "Design" / "Penpot"
PNG = OUT_DIR / "usa-stock-analysis-penpot-proposal.png"
PENPOT = OUT_DIR / "usa-stock-analysis-penpot-proposal.penpot"
BOARDS = [
    {
        "key": "hero",
        "name": "Desktop / Stock analysis hero - animation logo proposal",
        "png": OUT_DIR / "hero-proposal.png",
        "x": 0,
        "y": 0,
        "width": 1440,
        "height": 900,
    },
    {
        "key": "demo",
        "name": "Desktop / Demo video + features - empty video",
        "png": OUT_DIR / "demo-features-proposal.png",
        "x": 1580,
        "y": 0,
        "width": 1440,
        "height": 900,
    },
    {
        "key": "spec",
        "name": "Logo animation spec / awaiting approval",
        "png": OUT_DIR / "animation-spec-proposal.png",
        "x": 0,
        "y": 1060,
        "width": 1440,
        "height": 870,
    },
]


def uid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "usa-stock-analysis/" + value))


def rect_points(x, y, w, h):
    return [
        {"x": x, "y": y},
        {"x": x + w, "y": y},
        {"x": x + w, "y": y + h},
        {"x": x, "y": y + h},
    ]


def selrect(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h, "x1": x, "y1": y, "x2": x + w, "y2": y + h}


def matrix():
    return {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0}


def base_shape(shape_id, name, shape_type, x, y, w, h, parent_id, frame_id):
    return {
        "id": shape_id,
        "name": name,
        "type": shape_type,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "rotation": 0,
        "selrect": selrect(x, y, w, h),
        "points": rect_points(x, y, w, h),
        "transform": matrix(),
        "transformInverse": matrix(),
        "parentId": parent_id,
        "frameId": frame_id,
    }


def main():
    missing = [str(board["png"]) for board in BOARDS if not board["png"].exists()]
    if missing:
        raise SystemExit("Missing PNG crop(s): " + ", ".join(missing))

    file_id = uid("file")
    page_id = uid("page")
    root_id = "00000000-0000-0000-0000-000000000000"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    manifest = {
        "type": "penpot/export-files",
        "version": 1,
        "generatedBy": "codex/penpot-v3-package",
        "referer": "penpot",
        "files": [
            {
                "id": file_id,
                "name": "USA Stock Analysis - Animation Proposal",
                "features": [],
            }
        ],
        "relations": [],
    }

    file_json = {
        "id": file_id,
        "name": "USA Stock Analysis - Animation Proposal",
        "revn": 0,
        "vern": 0,
        "createdAt": now,
        "modifiedAt": now,
        "isShared": False,
        "hasMediaTrimmed": False,
        "version": 75,
        "features": [],
        "options": {
            "componentsV2": True,
            "baseFontSize": "16px",
        },
    }

    board_ids = [uid(f"{board['key']}-board") for board in BOARDS]
    root = base_shape(root_id, "Root Frame", "frame", 0, 0, 0.01, 0.01, root_id, root_id)
    root.update({
        "fills": [{"fillColor": "#FFFFFF", "fillOpacity": 1}],
        "strokes": [],
        "shapes": board_ids,
        "r1": 0,
        "r2": 0,
        "r3": 0,
        "r4": 0,
        "hideFillOnExport": False,
    })

    page = {
        "id": page_id,
        "name": "Animation Proposal",
        "index": 0,
        "background": "#010302",
    }

    files_prefix = f"files/{file_id}"
    page_prefix = f"{files_prefix}/pages/{page_id}"

    with zipfile.ZipFile(PENPOT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr(f"files/{file_id}.json", json.dumps(file_json, indent=2))
        zf.writestr(f"{page_prefix}.json", json.dumps(page, indent=2))
        zf.writestr(f"{page_prefix}/{root['id']}.json", json.dumps(root, indent=2))

        for board in BOARDS:
            board_id = uid(f"{board['key']}-board")
            image_shape_id = uid(f"{board['key']}-image-shape")
            media_object_id = uid(f"{board['key']}-media-object")
            storage_id = uid(f"{board['key']}-storage-object")
            png_bytes = board["png"].read_bytes()

            frame = base_shape(
                board_id,
                board["name"],
                "frame",
                board["x"],
                board["y"],
                board["width"],
                board["height"],
                root_id,
                root_id,
            )
            frame.update({
                "fills": [{"fillColor": "#010302", "fillOpacity": 1}],
                "strokes": [],
                "shapes": [image_shape_id],
                "r1": 0,
                "r2": 0,
                "r3": 0,
                "r4": 0,
                "hideFillOnExport": False,
                "showContent": True,
            })

            image_shape = base_shape(
                image_shape_id,
                board["name"] + " preview",
                "image",
                board["x"],
                board["y"],
                board["width"],
                board["height"],
                board_id,
                board_id,
            )
            image_shape.update({
                "fills": [
                    {
                        "fillImage": {
                            "id": media_object_id,
                            "width": board["width"],
                            "height": board["height"],
                            "mtype": "image/png",
                            "name": board["png"].name,
                            "keepAspectRatio": True,
                        },
                        "fillOpacity": 1,
                    }
                ],
                "strokes": [],
                "r1": 0,
                "r2": 0,
                "r3": 0,
                "r4": 0,
                "metadata": {
                    "id": media_object_id,
                    "width": board["width"],
                    "height": board["height"],
                    "mtype": "image/png",
                },
                "proportion": board["width"] / board["height"],
                "proportionLock": True,
            })

            media_json = {
                "id": media_object_id,
                "createdAt": now,
                "name": board["png"].name,
                "width": board["width"],
                "height": board["height"],
                "mtype": "image/png",
                "mediaId": storage_id,
                "isLocal": True,
            }

            storage_json = {
                "id": storage_id,
                "size": len(png_bytes),
                "contentType": "image/png",
                "bucket": "file-media-object",
            }

            zf.writestr(f"{page_prefix}/{frame['id']}.json", json.dumps(frame, indent=2))
            zf.writestr(f"{page_prefix}/{image_shape['id']}.json", json.dumps(image_shape, indent=2))
            zf.writestr(f"{files_prefix}/media/{media_object_id}.json", json.dumps(media_json, indent=2))
            zf.writestr(f"objects/{storage_id}.json", json.dumps(storage_json, indent=2))
            zf.writestr(f"objects/{storage_id}.png", png_bytes)

    print(PENPOT)


if __name__ == "__main__":
    main()
