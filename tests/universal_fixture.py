"""Model-facing browser fixtures use the same semantic DTO as production."""

import json
from semantic_fixture import world, campaign


def authoring_reply(prompt, request):
    title = json.loads(prompt.split("Верни только JSON по схеме:\n", 1)[1])["title"]
    if title == "SemanticSettingDTO":
        return world()
    if title == "SemanticCampaignDTO":
        return campaign()
    if title == "SemanticExpansionDTO":
        return {
            "locations": [
                {
                    "name": "Обсерватория",
                    "connections": [request["context"]["current_location"]],
                }
            ]
        }
    raise ValueError("Unknown semantic fixture stage: " + title)
