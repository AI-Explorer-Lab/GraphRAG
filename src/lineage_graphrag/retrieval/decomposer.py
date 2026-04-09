from __future__ import annotations


class LineageQuestionDecomposer:
    """Schema-aware lightweight question decomposition."""

    def decompose(self, question: str) -> dict[str, object]:
        question_l = question.lower()
        nodes: list[str] = []
        relations: list[str] = []
        attributes: list[str] = []

        if "transition" in question_l or "关系" in question:
            relations.append("transitions")
        if "属性" in question or "meaning" in question_l or "什么意思" in question:
            attributes.append("description")
        if "audit" in question_l or "审计" in question:
            nodes.append("control_service")
        if "recommendation" in question_l or "推荐" in question:
            nodes.append("feature_view")

        return {
            "sub_questions": [{"sub-question": question}],
            "involved_types": {
                "nodes": nodes,
                "relations": relations,
                "attributes": attributes,
            },
        }

