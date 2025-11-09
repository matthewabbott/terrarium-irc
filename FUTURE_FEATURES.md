# Future Features for Terra-irc

This document tracks aspirational features and improvements for future development sessions.

## Tool Use & Multi-Message Capability

**Status**: Not implemented
**Priority**: High (enables richer IRC interaction)

**Goal**: Allow Terra to send multiple messages in sequence, enabling interactions like:
- Sending IRC commands (e.g., `/names` to get channel member list)
- Multi-part responses when needed
- Proactive information gathering

**Implementation approach**:
- Implement tool calling loop similar to terrarium-agent
- Define IRC-specific tools:
  - `send_irc_command(command)` - Send raw IRC command
  - `send_message(channel, message)` - Send additional message
  - `search_chat_logs(query, timeframe)` - Already partially exists
- Agent can call tools, bot executes them, results fed back to agent
- Agent decides when to finish and send final response

**Considerations**:
- GLM-4.5-Air-4bit may struggle with tool use (less sophisticated than Claude)
- Need rate limiting to prevent flooding
- Should we allow unrestricted IRC commands or whitelist safe ones?

---

## RAG System for Chat Log Search

**Status**: Not implemented
**Priority**: Medium (useful but not critical)

**Goal**: Semantic search over chat history instead of just keyword matching.

**Implementation approach**:
- Embed IRC messages using a local embedding model
- Store vectors in SQLite (sqlite-vec) or separate vector DB
- Provide `semantic_search_chat_logs(query, limit)` tool
- Agent can find relevant past discussions even without exact keyword matches

**Example use case**:
```
User: "What did we discuss about deployment last month?"
Terra: [searches "deployment issues configuration problems" semantically]
       [finds relevant messages even if they said "pushing to prod" instead]
```

**Considerations**:
- Need embedding model (sentence-transformers?)
- Storage overhead (vectors for every message)
- Re-embedding existing chat logs
- Incremental updates as new messages arrive

---

## Context Summarization

**Status**: Not implemented
**Priority**: Low (only needed when we hit token limits in practice)

**Goal**: Compress old conversation history while preserving key information.

**Current approach**: Store everything, let token limits be the natural boundary

**Future approach when needed**:
- After N turns (e.g., 50), summarize older turns
- Keep recent 10-20 turns in full
- Store summary pointing to specific message IDs
- Agent can retrieve full details via tool if needed

**Implementation**:
```python
{
  "summary": {
    "created_at_turn": 50,
    "topics": [
      {"topic": "deployment", "keywords": ["docker", "staging"], "turn_ids": [5, 12, 18]},
      {"topic": "database migration", "keywords": ["postgres", "schema"], "turn_ids": [22, 25]}
    ],
    "text": "Earlier, we discussed deployment issues and database migrations..."
  },
  "recent_turns": [last 20 full turns],
  "current_turn": {...}
}
```

**Considerations**:
- When to summarize? (token count threshold? turn count?)
- How to preserve important details?
- Allow agent to request full details from summary via tool

---

## Multi-Agent Communication

**Status**: Not implemented
**Priority**: Low (infrastructure not ready)

**Goal**: Terra-irc can communicate with other Terrarium agents (coordinator, etc.)

**Vision**:
- Terra-coordinator wants to write newsletter about agent activities
- Coordinator: "Hey Terra-irc, what interesting discussions happened this week?"
- Terra-irc loads its context (or a fork), searches logs, summarizes
- Terra-coordinator receives summary, incorporates into newsletter

**Another use case**:
- User in #terrarium: "!summon_research_agent what were the best Python tutorials mentioned?"
- Terra-irc: [spawns or messages research agent with IRC log access]
- Research agent: [analyzes logs, finds tutorials, ranks them]
- Terra-irc: [receives results, formats for IRC, responds]

**Implementation approach**:
- Inter-agent message bus (HTTP? Redis pubsub? Direct API calls?)
- Context forking/sharing mechanism
- Agent registry (who's available, what they do)
- Request/response protocol

**Considerations**:
- Security (which agents can talk to which?)
- Context privacy (should all agents see all IRC logs?)
- Coordination complexity
- Need Terrarium coordinator/orchestrator first

---

## Scratchpad / Internal Thinking Storage

**Status**: Not implemented
**Priority**: Low (nice-to-have for debugging)

**Goal**: Store AI's internal reasoning (`<thinking>` tags) so it can review its past thought process.

**Implementation**:
```sql
ALTER TABLE conversation_history ADD COLUMN thinking TEXT;
```

**Use case**:
```
User: "Why did you suggest approach X yesterday?"
Terra: [searches history, finds message AND thinking]
       [sees: "I suggested X because I was thinking Y, but now I realize Z"]
       "Good question! Looking back at my reasoning..."
```

**Considerations**:
- Not all models produce thinking (need to parse or use specific prompts)
- Storage overhead
- Privacy (thinking can reveal model limitations)
- Usefulness varies by model

---

## Cross-Channel Awareness

**Status**: Isolated per-channel (by design)
**Priority**: Low (current isolation is clean)

**Current behavior**: Each channel has separate conversation context.

**Potential future behavior**:
- Terra in #test: "In #terrarium, we discussed..."
- Cross-reference discussions across channels
- Unified memory with channel tags

**Implementation**:
- Tool: `search_all_channels(query)` instead of just current channel
- Context injection could include relevant cross-channel info
- Privacy controls (some channels private?)

**Considerations**:
- Do users expect channel isolation?
- Context window blowup (more channels = more messages)
- Privacy (sensitive discussions in one channel leaked to another)

---

## Dynamic System Prompt Adjustment

**Status**: Static per-channel
**Priority**: Low (static works fine)

**Goal**: Adjust Terra's personality/behavior based on context.

**Examples**:
- In #terrarium (technical): More detailed, helpful, formal
- In #SomaIsGay (casual): Match the caustic/sarcastic tone
- Late night (< 5 users active): More conversational
- High activity (20+ messages/min): Ultra-concise

**Implementation**:
- Detect channel activity patterns
- Adjust system prompt dynamically
- Learn from user feedback (tone preferences)

**Considerations**:
- Complexity vs. benefit tradeoff
- Risk of inconsistent personality
- User preference varies

---

## Persistent User Preferences

**Status**: Not implemented
**Priority**: Low (nice-to-have)

**Goal**: Remember per-user preferences.

**Examples**:
```sql
CREATE TABLE user_preferences (
    nick TEXT PRIMARY KEY,
    preferred_response_length TEXT, -- 'short', 'medium', 'long'
    tone TEXT, -- 'casual', 'formal', 'technical'
    topics_of_interest TEXT[] -- ['python', 'deployment', 'gaming']
);
```

**Use case**:
```
Alice: "!terrarium what is Python?" [gets long, detailed response]
Bob: "!terrarium what is Python?" [knows Bob prefers concise, gives short answer]
```

**Considerations**:
- How to learn preferences? (explicit commands? implicit from reactions?)
- Privacy (storing user preferences)
- Maintenance (preferences drift over time)

---

## Integration with External Services

**Status**: Not implemented
**Priority**: Low (depends on use cases)

**Potential integrations**:
- GitHub: "!terrarium what PRs are open?"
- Docs: "!terrarium search Python docs for decorators"
- Web search: "!terrarium what's the current Python version?"
- Calendar: "!terrarium when's the next meeting?"

**Implementation**:
- Tools for each service
- API credentials (stored securely)
- Rate limiting, caching

**Considerations**:
- Security (API keys in env vars?)
- Cost (API usage)
- Reliability (external service downtime)

---

## Analytics & Insights

**Status**: Basic `!stats` command exists
**Priority**: Low (not critical)

**Goal**: Richer analytics about IRC activity and Terra usage.

**Examples**:
- "!stats detailed" → Most active users, peak times, common topics
- "!terra-usage" → How often Terra is invoked, response times, popular queries
- Daily/weekly summary posts
- Sentiment analysis (are convos getting heated?)

**Implementation**:
- Background job to analyze logs
- Store insights in separate tables
- Visualization (IRC art charts? web dashboard?)

**Considerations**:
- Privacy (analyzing user behavior)
- Storage (aggregated stats tables)
- Computational cost (analysis jobs)

---

## Notes

- Features listed here are **aspirational**, not commitments
- Priority may change based on actual usage patterns
- Implementation details are preliminary and subject to change
- Add new ideas to this doc as they come up
- Review periodically and adjust priorities

**Last updated**: 2025-11-08
