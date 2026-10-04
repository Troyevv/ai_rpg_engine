"""Model-facing browser fixtures use the same semantic DTO as production."""

import json
from semantic_fixture import world_blueprint as world, campaign_blueprint as campaign


def authoring_reply(prompt, request):
    title = json.loads(prompt.split("Верни только JSON по схеме:\n", 1)[1])["title"]
    if title == "WorldBlueprint":
        return world()
    if title == "CampaignBlueprint":
        return campaign()
    if title == "ExpansionBlueprint":
        return {
            "locations": [
                {
                    "name": "Обсерватория",
                }
            ]
        }
    raise ValueError("Unknown semantic fixture stage: " + title)
