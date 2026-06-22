#!/usr/bin/env python3
"""
Generate XMind test-case files from structured JSON.

Supported input schemas:

Platform-first structure:
{
  "project_name": "Project test cases",
  "platforms": [
    {
      "name": "iOS",
      "modules": [
        {
          "name": "Module name",
          "cases": [
            {
              "title": "Case title",
              "purpose": "What this case verifies",
              "prerequisites": ["Optional precondition"],
              "steps": ["Step 1", "Step 2"],
              "expected": ["Expected 1", "Expected 2"]
            }
          ]
        }
      ]
    }
  ]
}

Legacy structure:
{
  "project_name": "Project test cases",
  "modules": [
    {
      "name": "Module name",
      "cases": [
        {
          "title": "Case title",
          "purpose": "What this case verifies",
          "prerequisites": ["Optional precondition"],
          "steps": ["Step 1", "Step 2"],
          "expected": ["Expected 1", "Expected 2"]
        }
      ]
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET


CONTENT_NS = "urn:xmind:xmap:xmlns:content:2.0"
STYLES_NS = "urn:xmind:xmap:xmlns:styles:2.0"
CREATOR = "ty-case-test"
REQUIRED_XMIND_FILES = {
    "content.xml",
    "meta.xml",
    "styles.xml",
    "META-INF/manifest.xml",
}


def now_ms() -> str:
    return str(int(datetime.now().timestamp() * 1000))


def generate_uuid() -> str:
    return uuid.uuid4().hex[:24]


def as_non_empty_string(value: Any, path: str, errors: List[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    errors.append(f"{path} must be a non-empty string")
    return ""


def normalize_optional_list(value: Any, path: str, errors: List[str]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: List[str] = []
        for index, item in enumerate(value):
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            else:
                errors.append(f"{path}[{index}] must be a non-empty string")
        return result
    errors.append(f"{path} must be a string or a list of strings")
    return []


def normalize_required_list(value: Any, path: str, errors: List[str]) -> List[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a non-empty list of strings")
        return []
    if not value:
        errors.append(f"{path} must not be empty")
        return []

    result: List[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        else:
            errors.append(f"{path}[{index}] must be a non-empty string")
    return result


def validate_case(case: Any, case_path: str, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(case, dict):
        errors.append(f"{case_path} must be an object")
        return

    as_non_empty_string(case.get("title"), f"{case_path}.title", errors)
    as_non_empty_string(case.get("purpose"), f"{case_path}.purpose", errors)

    steps = normalize_required_list(case.get("steps"), f"{case_path}.steps", errors)
    expected = normalize_required_list(case.get("expected"), f"{case_path}.expected", errors)
    normalize_optional_list(case.get("prerequisites"), f"{case_path}.prerequisites", errors)

    if steps and expected and len(steps) != len(expected):
        warnings.append(
            f"{case_path}: steps count ({len(steps)}) and expected count ({len(expected)}) differ"
        )


def validate_module(module: Any, module_path: str, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(module, dict):
        errors.append(f"{module_path} must be an object")
        return

    as_non_empty_string(module.get("name"), f"{module_path}.name", errors)
    cases = module.get("cases")
    if not isinstance(cases, list):
        errors.append(f"{module_path}.cases must be a list")
        return
    if not cases:
        warnings.append(f"{module_path}.cases is empty")
        return

    for case_index, case in enumerate(cases):
        validate_case(case, f"{module_path}.cases[{case_index}]", errors, warnings)


def validate_platform(platform: Any, platform_path: str, errors: List[str], warnings: List[str]) -> None:
    if not isinstance(platform, dict):
        errors.append(f"{platform_path} must be an object")
        return

    as_non_empty_string(platform.get("name"), f"{platform_path}.name", errors)
    modules = platform.get("modules")
    if not isinstance(modules, list):
        errors.append(f"{platform_path}.modules must be a list")
        return
    if not modules:
        warnings.append(f"{platform_path}.modules is empty")
        return

    for module_index, module in enumerate(modules):
        validate_module(module, f"{platform_path}.modules[{module_index}]", errors, warnings)


def validate_cases_data(data: Any) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(data, dict):
        return ["root must be a JSON object"], warnings

    as_non_empty_string(data.get("project_name"), "project_name", errors)

    has_platforms = "platforms" in data
    has_modules = "modules" in data
    if has_platforms and has_modules:
        errors.append("top-level platforms and modules cannot both be provided")
        return errors, warnings
    if not has_platforms and not has_modules:
        errors.append("provide either top-level platforms or modules")
        return errors, warnings

    if has_platforms:
        platforms = data.get("platforms")
        if not isinstance(platforms, list):
            errors.append("platforms must be a non-empty list")
            return errors, warnings
        if not platforms:
            errors.append("platforms must not be empty")
            return errors, warnings

        for platform_index, platform in enumerate(platforms):
            validate_platform(platform, f"platforms[{platform_index}]", errors, warnings)
        return errors, warnings

    modules = data.get("modules")
    if not isinstance(modules, list):
        errors.append("modules must be a non-empty list")
        return errors, warnings
    if not modules:
        errors.append("modules must not be empty")
        return errors, warnings

    for module_index, module in enumerate(modules):
        validate_module(module, f"modules[{module_index}]", errors, warnings)

    return errors, warnings


def normalize_case(case: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": case["title"].strip(),
        "purpose": case["purpose"].strip(),
        "prerequisites": normalize_optional_list(case.get("prerequisites"), "prerequisites", []),
        "steps": normalize_required_list(case.get("steps"), "steps", []),
        "expected": normalize_required_list(case.get("expected"), "expected", []),
    }


def normalize_module(module: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": module["name"].strip(),
        "cases": [normalize_case(case) for case in module.get("cases", [])],
    }


def normalize_platform(platform: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": platform["name"].strip(),
        "modules": [normalize_module(module) for module in platform.get("modules", [])],
    }


def normalize_cases_data(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {
        "project_name": data["project_name"].strip(),
    }

    if "platforms" in data:
        normalized["structure"] = "platforms"
        normalized["platforms"] = [normalize_platform(platform) for platform in data["platforms"]]
    else:
        normalized["structure"] = "modules"
        normalized["modules"] = [normalize_module(module) for module in data["modules"]]

    return normalized


def collect_stats(normalized: Dict[str, Any]) -> Dict[str, int]:
    if normalized["structure"] == "platforms":
        platform_count = len(normalized["platforms"])
        module_count = sum(len(platform["modules"]) for platform in normalized["platforms"])
        case_count = sum(
            len(module["cases"])
            for platform in normalized["platforms"]
            for module in platform["modules"]
        )
        return {
            "platform_count": platform_count,
            "module_count": module_count,
            "case_count": case_count,
        }

    module_count = len(normalized["modules"])
    case_count = sum(len(module["cases"]) for module in normalized["modules"])
    return {
        "platform_count": 0,
        "module_count": module_count,
        "case_count": case_count,
    }


def add_title(parent: ET.Element, title: str) -> None:
    title_node = ET.SubElement(parent, "title")
    title_node.text = title


def build_topic(
    title: str,
    children: Optional[Iterable[ET.Element]] = None,
    *,
    branch: Optional[str] = None,
    structure_class: Optional[str] = None,
) -> ET.Element:
    attrs = {
        "id": generate_uuid(),
        "modified-by": CREATOR,
        "timestamp": now_ms(),
    }
    if branch:
        attrs["branch"] = branch
    if structure_class:
        attrs["structure-class"] = structure_class

    topic = ET.Element("topic", attrs)
    add_title(topic, title)

    child_topics = list(children or [])
    if child_topics:
        children_node = ET.SubElement(topic, "children")
        topics_node = ET.SubElement(children_node, "topics", {"type": "attached"})
        for child in child_topics:
            topics_node.append(child)

    return topic


def build_case_topic(case: Dict[str, Any]) -> ET.Element:
    steps_text = "测试步骤：\n" + "\n".join(
        f"{index + 1}、{step}" for index, step in enumerate(case["steps"])
    )
    expected_text = "预期结果：\n" + "\n".join(
        f"{index + 1}、{result}" for index, result in enumerate(case["expected"])
    )
    expected_topic = build_topic(expected_text)
    steps_topic = build_topic(steps_text, [expected_topic])
    prerequisites = case["prerequisites"] or ["无"]
    prerequisite_topic = build_topic("前置条件：" + "；".join(prerequisites), [steps_topic])
    return build_topic("测试目的：" + case["purpose"], [prerequisite_topic])


def build_module_topic(module: Dict[str, Any]) -> ET.Element:
    case_topics = [build_case_topic(case) for case in module["cases"]]
    return build_topic(module["name"], case_topics)


def build_content_xml(data: Dict[str, Any]) -> bytes:
    root = ET.Element(
        "xmap-content",
        {
            "xmlns": CONTENT_NS,
            "xmlns:fo": "http://www.w3.org/1999/XSL/Format",
            "xmlns:svg": "http://www.w3.org/2000/svg",
            "xmlns:xhtml": "http://www.w3.org/1999/xhtml",
            "xmlns:xlink": "http://www.w3.org/1999/xlink",
            "modified-by": CREATOR,
            "timestamp": now_ms(),
            "version": "2.0",
        },
    )

    sheet = ET.SubElement(
        root,
        "sheet",
        {
            "id": generate_uuid(),
            "modified-by": CREATOR,
            "timestamp": now_ms(),
        },
    )

    root_topics: List[ET.Element] = []
    if data["structure"] == "platforms":
        for platform in data["platforms"]:
            module_topics = [build_module_topic(module) for module in platform["modules"]]
            root_topics.append(build_topic(platform["name"], module_topics))
    else:
        root_topics = [build_module_topic(module) for module in data["modules"]]

    sheet.append(
        build_topic(
            data["project_name"],
            root_topics,
            structure_class="org.xmind.ui.logic.right",
        )
    )

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_meta_xml(title: str) -> bytes:
    root = ET.Element("meta")
    file_hash = ET.SubElement(root, "file-hash")
    file_hash.text = generate_uuid()[:8]

    creator = ET.SubElement(root, "creator")
    creator_name = ET.SubElement(creator, "name")
    creator_name.text = CREATOR
    creator_version = ET.SubElement(creator, "version")
    creator_version.text = "1.0"

    created_time = ET.SubElement(root, "created-time")
    created_time.text = datetime.now().isoformat()

    description = ET.SubElement(root, "description")
    description.text = f"测试用例：{title}"

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_styles_xml() -> bytes:
    root = ET.Element("xmap-styles", {"xmlns": STYLES_NS})
    ET.SubElement(root, "styles")
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_manifest_xml() -> bytes:
    root = ET.Element("manifest")
    entries = [
        ("content.xml", "text/xml"),
        ("meta.xml", "text/xml"),
        ("styles.xml", "text/xml"),
    ]
    for full_path, media_type in entries:
        ET.SubElement(root, "file-entry", {"full-path": full_path, "media-type": media_type})
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def create_xmind(data: Dict[str, Any], output_path: Path) -> Dict[str, int]:
    errors, warnings = validate_cases_data(data)
    if errors:
        raise ValueError("; ".join(errors))

    normalized = normalize_cases_data(data)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as xmind:
        xmind.writestr("content.xml", build_content_xml(normalized))
        xmind.writestr("meta.xml", build_meta_xml(normalized["project_name"]))
        xmind.writestr("styles.xml", build_styles_xml())
        xmind.writestr("META-INF/manifest.xml", build_manifest_xml())

    stats = validate_xmind_file(output_path)
    stats["warnings"] = len(warnings)
    stats.update(collect_stats(normalized))
    return stats


def validate_xmind_file(output_path: Path) -> Dict[str, int]:
    output_path = Path(output_path)
    if not output_path.exists():
        raise ValueError(f"output file does not exist: {output_path}")
    if not zipfile.is_zipfile(output_path):
        raise ValueError(f"output file is not a valid zip/XMind package: {output_path}")

    with zipfile.ZipFile(output_path, "r") as xmind:
        names = set(xmind.namelist())
        missing = sorted(REQUIRED_XMIND_FILES - names)
        if missing:
            raise ValueError(f"XMind package is missing required files: {', '.join(missing)}")

        content = xmind.read("content.xml")

    xml_root = ET.fromstring(content)
    topic_count = sum(1 for elem in xml_root.iter() if elem.tag.endswith("topic"))
    title_count = sum(1 for elem in xml_root.iter() if elem.tag.endswith("title") and elem.text and elem.text.strip())
    if topic_count == 0:
        raise ValueError("content.xml contains no topic nodes")
    if title_count == 0:
        raise ValueError("content.xml contains no title nodes")

    return {
        "topic_count": topic_count,
        "title_count": title_count,
    }


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input file is not valid JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("input JSON root must be an object")
    return data


def sample_data() -> Dict[str, Any]:
    return {
        "project_name": "多端搜索功能测试用例",
        "platforms": [
            {
                "name": "iOS",
                "modules": [
                    {
                        "name": "入口",
                        "cases": [
                            {
                                "title": "验证 iOS 首页搜索入口展示",
                                "purpose": "验证 iOS 首页顶部搜索入口按配置正常展示",
                                "prerequisites": ["后台已开启 iOS 首页搜索入口配置"],
                                "steps": ["打开 iOS 端 App 并进入首页", "查看页面顶部搜索区域"],
                                "expected": ["首页加载完成", "顶部展示搜索框、购物车入口和消息入口"],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Android外发包",
                "modules": [
                    {
                        "name": "暗纹词",
                        "cases": [
                            {
                                "title": "验证 Android外发包暗纹词每 3 秒轮播",
                                "purpose": "验证 Android外发包搜索框暗纹词按算法返回内容每 3 秒轮播展示",
                                "prerequisites": ["后台已配置 3 条暗纹词", "算法接口正常返回暗纹词"],
                                "steps": ["进入 Android外发包首页", "查看搜索框暗纹词", "等待 3 秒", "再次查看暗纹词"],
                                "expected": ["首页加载完成", "展示第 1 条暗纹词", "等待期间页面无卡顿", "暗纹词切换为下一条并循环展示"],
                            }
                        ],
                    }
                ],
            },
        ],
    }


def print_validation_result(data: Dict[str, Any], warnings: List[str]) -> None:
    normalized = normalize_cases_data(data)
    stats = collect_stats(normalized)
    print(
        "Validation passed: "
        f"platforms={stats['platform_count']}, modules={stats['module_count']}, "
        f"cases={stats['case_count']}, warnings={len(warnings)}"
    )
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an XMind test-case file from structured JSON.")
    parser.add_argument("--input", type=Path, help="Path to the input test-case JSON file.")
    parser.add_argument("--output", type=Path, help="Path to the output .xmind file.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the output file if it already exists.")
    parser.add_argument("--validate-only", action="store_true", help="Validate input JSON without generating XMind.")
    parser.add_argument("--demo", action="store_true", help="Use built-in demo data instead of --input.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.demo:
        data = sample_data()
    elif args.input:
        try:
            data = load_json(args.input)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        print("Error: provide --input <json> or --demo", file=sys.stderr)
        return 1

    errors, warnings = validate_cases_data(data)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.validate_only:
        print_validation_result(data, warnings)
        return 0

    if not args.output:
        print("Error: provide --output <xmind> when not using --validate-only", file=sys.stderr)
        return 1

    if args.output.exists() and not args.overwrite:
        print(f"Error: output already exists, pass --overwrite to replace it: {args.output}", file=sys.stderr)
        return 1

    try:
        stats = create_xmind(data, args.output)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    print(
        "Generated XMind: "
        f"path={args.output}, platforms={stats['platform_count']}, "
        f"modules={stats['module_count']}, cases={stats['case_count']}, "
        f"topics={stats['topic_count']}, warnings={len(warnings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
