"""The exact shape the parser model must answer in (structured outputs).

The SDK turns these pydantic classes into a JSON schema, the API makes the model
follow it, and the SDK validates the answer back into these classes. So we never
read free-form model text (CLAUDE.md: never regex-parse model text).
"""

from typing import Literal

from pydantic import BaseModel, Field

from reminderbot.core.when import WhenSpec


class ParsedItem(BaseModel):
    title: str = Field(
        description='Short task name in the user\'s words, e.g. "Data Structures assignment". '
        "Empty if the message only gives a time."
    )
    kind: Literal["deadline", "at_time"] = Field(
        description='"deadline" for things that are due (assignment, quiz, exam, submission). '
        '"at_time" for "remind me at/in ... to do X".'
    )
    when: WhenSpec
    confidence: float = Field(
        description="0.0-1.0: how sure you are that you described the day the student meant. "
        "A missing time is NOT a reason for low confidence (we default to 8:00 AM)."
    )


class ParsedMessage(BaseModel):
    intent: Literal["reminder", "question", "other"] = Field(
        description='"reminder" if the user wants to be reminded of something, '
        '"question" if they are asking something, "other" for anything else.'
    )
    items: list[ParsedItem] = Field(description="One entry per task. Empty unless intent=reminder.")
