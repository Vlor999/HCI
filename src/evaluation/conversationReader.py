import os
import re
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ConversationEntry:
    question: str
    answer: str
    question_number: int


@dataclass
class ConversationLog:
    filename: str
    timestamp: datetime
    path_description: str
    additional_facts: List[str]
    conversations: List[ConversationEntry]


class ConversationReader:
    def __init__(self, log_dir: str = "log/conversations"):
        self.log_dir = log_dir

    def read_all_conversations(self) -> List[ConversationLog]:
        conversations: List[ConversationLog] = []
        if not os.path.exists(self.log_dir):
            return conversations

        for filename in os.listdir(self.log_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(self.log_dir, filename)
                conversation = self.parse_conversation_file(filepath)
                if conversation:
                    conversations.append(conversation)

        return sorted(conversations, key=lambda x: x.timestamp, reverse=True)

    def parse_conversation_file(self, filepath: str) -> Optional[ConversationLog]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            filename = os.path.basename(filepath)
            timestamp = self.extract_timestamp_from_filename(filename)
            path_description = self.extract_path_description(content)
            additional_facts = self.extract_additional_facts(content)
            conversations = self.extract_conversations(content)

            return ConversationLog(
                filename=filename,
                timestamp=timestamp,
                path_description=path_description,
                additional_facts=additional_facts,
                conversations=conversations,
            )
        except Exception as e:
            print(f"Error parsing conversation file {filepath}: {e}")
            return None

    def extract_timestamp_from_filename(self, filename: str) -> datetime:
        try:
            timestamp_match = re.search(r"(\d{8}_\d{6})", filename)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        except Exception:
            pass
        return datetime.now()

    def extract_path_description(self, content: str) -> str:
        path_match = re.search(r"## Path\n\n```\n(.*?)\n```", content, re.DOTALL)
        return path_match.group(1).strip() if path_match else ""

    def extract_additional_facts(self, content: str) -> List[str]:
        facts = []
        facts_match = re.search(r"## Additional facts and updates\n\n(.*?)\n\n", content, re.DOTALL)
        if facts_match:
            facts_text = facts_match.group(1)
            facts = [line.strip()[2:] for line in facts_text.split("\n") if line.strip().startswith("-")]
        return facts

    def extract_conversations(self, content: str) -> List[ConversationEntry]:
        conversations: List[ConversationEntry] = []
        qa_pattern = r"### Q(\d+): (.*?)\n\n\*\*Answer:\*\*\n\n(.*?)(?=\n\n###|\Z)"
        matches = re.findall(qa_pattern, content, re.DOTALL)

        for match in matches:
            question_num = int(match[0])
            question = match[1].strip()
            answer = match[2].strip()
            conversations.append(ConversationEntry(question, answer, question_num))

        return conversations
