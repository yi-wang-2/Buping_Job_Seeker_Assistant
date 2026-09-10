from __future__ import annotations

from typing import Any

from ....presentation import (
    CalloutBlock,
    DetailItem,
    DetailListBlock,
    FollowUpBlock,
    HeadingBlock,
    ResponseDocument,
)


class ResumeReviewPresenter:
    """Own the resume-review semantic layout; rendering stays domain agnostic."""

    def present(self, output: Any, *, inputs: dict[str, Any]) -> ResponseDocument:
        data = dict(output or {})
        zh = inputs.get("language") != "en"
        blocks: list[Any] = [
            HeadingBlock("总体评价" if zh else "Overall assessment"),
            CalloutBlock(str(data.get("overall_summary") or (
                "已完成整份简历评审。" if zh else "The full resume review is complete."
            ))),
        ]
        groups = (
            ("优点" if zh else "Strengths", data.get("strengths", [])),
            ("待改进项" if zh else "Areas to improve", data.get("weaknesses", [])),
        )
        for heading, findings in groups:
            if not findings:
                continue
            blocks.extend((
                HeadingBlock(heading),
                DetailListBlock(tuple(
                    DetailItem(
                        title=str(item.get("title") or ""),
                        label=str(item.get("section") or ("整份简历" if zh else "Full resume")),
                        body=str(item.get("analysis") or ""),
                        quote=("依据：" if zh else "Evidence: ") + str(item.get("evidence_quote") or ""),
                    )
                    for item in findings
                )),
            ))
        priorities = data.get("priorities", [])
        if priorities:
            priority_labels = (
                {"high": "高", "medium": "中", "low": "低"}
                if zh else {"high": "High", "medium": "Medium", "low": "Low"}
            )
            blocks.extend((
                HeadingBlock("修改优先级" if zh else "Revision priorities"),
                DetailListBlock(tuple(
                    DetailItem(
                        title=(
                            f"{priority_labels.get(item.get('priority', 'medium'), item.get('priority', 'medium'))}："
                            f"{item.get('action', '')}"
                        ),
                        body=str(item.get("reason") or ""),
                    )
                    for item in priorities
                )),
            ))
        blocks.append(FollowUpBlock(self._follow_up(data, inputs, zh=zh)))
        return ResponseDocument(tuple(blocks))

    @staticmethod
    def _follow_up(data: dict[str, Any], inputs: dict[str, Any], *, zh: bool) -> str:
        sections = []
        for item in data.get("weaknesses", []):
            section = str(item.get("section") or "").strip()
            if section and section not in sections:
                sections.append(section)
        targets = sections[:2]
        if zh:
            choices = "或".join(f"「{section}」" for section in targets)
            if choices:
                return f"需要我按照上述优先级帮你修改吗？可以先从{choices}开始，也可以让我给出整版修改方案。"
            return "需要我按照上述优先级帮你修改吗？你可以指定一个模块，也可以让我给出整版修改方案。"
        choices = " or ".join(f'“{section}”' for section in targets)
        if choices:
            return f"Would you like me to revise it in this order? We can start with {choices}, or I can propose a full revision."
        return "Would you like me to revise it in this order? Choose a section, or ask for a full revision."
