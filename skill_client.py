"""Skill management for loading and retrieving prompt skills."""

import os
from enum import Enum

from config import AppConfig


class SkillResult(Enum):
    """Enum representing special results from skill lookups."""

    NOT_FOUND = "not_found"


class SkillManager:
    """Loads and provides access to named skills from the filesystem."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.root = os.path.expanduser(config.skills.root)
        self.skills: dict[str, str] = {}

    def load_skills(self):
        """Load all skills from the configured skills directory."""
        print(f"Loading skills from {self.root}...")
        if not os.path.exists(self.root):
            print(f"Skills directory '{self.root}' does not exist. Creating it.")
            os.makedirs(self.root)

        for entry in os.scandir(self.root):
            if not entry.is_dir():
                continue
            skill_file = os.path.join(entry.path, "SKILL.md")
            if not os.path.isfile(skill_file):
                print(f"\tSkipping '{entry.name}': no SKILL.md found")
                continue
            with open(skill_file, encoding="utf-8") as f:
                content = f.read()
            self.skills[entry.name] = content
            print(f"\tLoaded skill: {entry.name}")

        print(f"Total skills loaded: {len(self.skills)}")

    def get_skill(self, skill_name: str) -> str | SkillResult:
        """Return skill content by name, or SkillResult.NOT_FOUND if not present."""
        content = self.skills.get(skill_name)
        if content is None:
            return SkillResult.NOT_FOUND
        return content
