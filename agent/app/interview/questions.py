from typing import List
from app.interview.models import Question

QUESTION_BANK: List[Question] = [
    Question(
        id="q1",
        title="Two Sum Variation",
        problem_statement="Given an array of integers and a target sum, return all unique pairs that add up to the target.",
        difficulty="junior",
        competency="data_structures",
        expected_concepts=["hash_map", "time_complexity_O(N)"],
        hints=[
            "Can you think of a data structure to store elements we've already seen?",
            "What if we used a Hash Set to check if (target - current_element) exists?",
            "Use a set to store visited numbers. For each number, check if the complement is in the set.",
            "Here is a strong hint: iterate the array, calculate complement = target - num. If complement in set, add pair to results, else add num to set."
        ],
        follow_up_topics=["What if the array is already sorted?", "How do you handle duplicates?"],
        time_budget_minutes=10,
        coding_required=True
    ),
    Question(
        id="q2",
        title="LRU Cache",
        problem_statement="Design and implement a data structure for Least Recently Used (LRU) cache.",
        difficulty="mid",
        competency="algorithms",
        expected_concepts=["doubly_linked_list", "hash_map", "O(1)_operations"],
        hints=[
            "We need O(1) lookups and O(1) evictions. What structures provide these?",
            "A dictionary provides O(1) lookup. How can we keep track of the 'least recently used' order in O(1)?",
            "Think about combining a Hash Map with a Doubly Linked List.",
            "Store the keys in the Hash Map pointing to nodes in a Doubly Linked List. When accessed, move the node to the head."
        ],
        follow_up_topics=["Is your solution thread-safe?", "How would you handle concurrent access?"],
        time_budget_minutes=15,
        coding_required=True
    ),
    Question(
        id="q3",
        title="System Design: Rate Limiter",
        problem_statement="Design a distributed API rate limiter.",
        difficulty="senior",
        competency="system_design",
        expected_concepts=["token_bucket", "redis", "distributed_systems", "concurrency"],
        hints=[
            "What algorithms exist for rate limiting? (e.g. Token Bucket, Leaky Bucket).",
            "How do we handle state across multiple API servers?",
            "Consider using a centralized data store like Redis to hold the counters.",
            "Use Redis with Lua scripts to ensure atomicity of the get-and-increment operations."
        ],
        follow_up_topics=["How do you handle Redis failure?", "What about clock synchronization across servers?"],
        time_budget_minutes=20,
        coding_required=False
    )
]

def get_questions_by_competency(competency: str, difficulty: str) -> List[Question]:
    """Filter questions based on competency and difficulty."""
    return [q for q in QUESTION_BANK if q.competency == competency and q.difficulty == difficulty]
