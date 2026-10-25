"""Buyer agent's private negotiation policy."""

from demo_agents.brain import AgentBrain, AgentPolicy


def create_agent():
    return AgentBrain(AgentPolicy(
        role="buyer",
        target=15,
        limit=35,
        concession=5,
        max_rounds=8
    ))
