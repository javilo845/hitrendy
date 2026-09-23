import pytest
from pydantic import ValidationError

from app.domain.models import GeneratedSocialPost


def test_social_post_rejects_more_than_five_hashtags() -> None:
    with pytest.raises(ValidationError):
        GeneratedSocialPost(
            platform="instagram",
            hook="Hook",
            caption="Caption",
            call_to_action="CTA",
            hashtags=["#1", "#2", "#3", "#4", "#5", "#6"],
            visual_direction="Visual",
            format_recommendation="reel",
            assumptions=[],
        )
