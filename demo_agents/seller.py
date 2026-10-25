"""Seller agent's private negotiation policy."""

from demo_agents.brain import AgentBrain, AgentPolicy


def create_agent():
    return AgentBrain(AgentPolicy(
        role="seller",
        target=40,
        limit=30,
        concession=5,
        max_rounds=8
    ))
