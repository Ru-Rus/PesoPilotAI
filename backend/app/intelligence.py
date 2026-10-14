"""Local statistical intelligence and allowlisted, read-only financial answers.

Descriptions are tokenized as data. No model ever executes SQL or writes finance.
Optional Ollama selects existing fact IDs only; backend generates every figure.
"""
import math
import json
import asyncio
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, extract
from sqlalchemy.orm import Session
from .auth import owner, rate_limit
from .db import session, settings
from .finance import CATEGORIES
from .models import Transaction, Budget, ModelConsent, Refund

router = APIRouter()


def month_start(value):
    if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', value):
        raise HTTPException(422, 'Month must be YYYY-MM')
    try:
        start = date.fromisoformat(value + '-01')
        if not 2 <= start.year <= 9998:
            raise ValueError()
        return start
    except ValueError:
        raise HTTPException(422, 'Unsupported month')


def shift_month(start, offset):
    index = start.year * 12 + start.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def tokens(value):
    return re.findall(r'[a-z]{2,24}', value.lower())[:40]


class CategorySuggestion(BaseModel):
    category: str | None
    confidence: float = Field(ge=0, le=1)
    examples: int = Field(ge=0)
    method: Literal['local_multinomial_naive_bayes'] = 'local_multinomial_naive_bayes'
    reason: str


def categorize(description, history):
    counts, documents = defaultdict(Counter), Counter()
    for text, category in history:
        if category in CATEGORIES:
            counts[category].update(tokens(text))
            documents[category] += 1
    vocabulary = set().union(*(set(c) for c in counts.values())) if counts else set()
    query = [token for token in tokens(description) if token in vocabulary]
    total = sum(documents.values())
    if not query or total < 2:
        return CategorySuggestion(category=None, confidence=0, examples=total, reason='Not enough matching approved history. Choose a category yourself.')
    scores = {}
    for category, count in counts.items():
        # Jeffreys smoothing avoids overwhelming small approved histories.
        denominator = sum(count.values()) + 0.5 * len(vocabulary)
        scores[category] = math.log(documents[category] / total) + sum(math.log((count[t] + 0.5) / denominator) for t in query)
    best = max(scores, key=scores.get)
    posterior = 1 / sum(math.exp(score - scores[best]) for score in scores.values())
    confidence = round(min(posterior, 0.95), 4)
    suggested = best if confidence >= 0.65 and documents[best] >= 2 else None
    return CategorySuggestion(category=suggested, confidence=confidence, examples=total, reason='Relative evidence score from your saved categories, not a guarantee. Review before applying.')


class Fact(BaseModel):
    id: str
    kind: Literal['summary', 'budget', 'change', 'anomaly', 'recurring']
    title: str
    amount_minor: int
    baseline_minor: int | None = None
    category: str | None = None
    source_description: str | None = None
    evidence_count: int = Field(default=0, ge=0)
    explanation: str


class InsightResult(BaseModel):
    month: str
    income_minor: int
    expense_minor: int
    net_minor: int
    facts: list[Fact]
    limitations: str = 'Based on recorded PHP transactions only. Patterns are candidates, not predictions or investment advice. Missing history limits comparisons.'


def insights(db, user, month):
    start = month_start(month)
    end = shift_month(start, 1)
    beginning = shift_month(start, -6)
    year, number = extract('year', Transaction.occurred_at), extract('month', Transaction.occurred_at)
    totals = db.execute(select(year, number, Transaction.kind, Transaction.category, func.sum(Transaction.amount_minor), func.count()).where(
        Transaction.user_id == user, Transaction.occurred_at >= beginning, Transaction.occurred_at < end).group_by(year, number, Transaction.kind, Transaction.category)).all()
    values, counts = {}, {}
    income = expense = 0
    for y, m, kind, category, amount, count in totals:
        if date(y, m, 1) == start:
            if kind == 'income':
                income += amount
            elif kind == 'expense':
                expense += amount
        if kind == 'expense':
            values[(y, m, category)] = amount
            counts[(y, m, category)] = count
    for y, m, category, amount in db.execute(select(extract('year', Refund.occurred_at), extract('month', Refund.occurred_at), Refund.category, func.sum(Refund.amount_minor)).where(Refund.user_id == user, Refund.occurred_at >= beginning, Refund.occurred_at < end).group_by(extract('year', Refund.occurred_at), extract('month', Refund.occurred_at), Refund.category)):
        values[(y, m, category)] = values.get((y, m, category), 0) - amount
        if date(y, m, 1) == start:
            expense -= amount
    facts = [Fact(id='summary', kind='summary', title='Monthly expenses', amount_minor=expense,
        explanation='Sum of recorded expense entries for this month; income and opening balances are excluded.')]
    for budget in db.scalars(select(Budget).where(Budget.user_id == user, Budget.month == month)):
        spent = values.get((start.year, start.month, budget.category), 0)
        if spent > budget.limit_minor:
            facts.append(Fact(id='budget:' + budget.category, kind='budget', title='Budget overrun', category=budget.category,
                amount_minor=spent - budget.limit_minor, baseline_minor=budget.limit_minor, explanation='Recorded spending minus the saved limit. Review discretionary entries; no future savings are guaranteed.'))
    previous = shift_month(start, -1)
    for category in CATEGORIES:
        current = values.get((start.year, start.month, category), 0)
        baseline = values.get((previous.year, previous.month, category), 0)
        if baseline > 0 and abs(current - baseline) >= 10000 and abs(current - baseline) * 2 >= baseline:
            facts.append(Fact(id='change:' + category, kind='change', title='Category change', category=category, amount_minor=current - baseline,
                baseline_minor=baseline, explanation='Difference from the previous recorded month; at least PHP 100 and 50% of the baseline.'))
        history = [values.get((d.year, d.month, category), 0) for d in (shift_month(start, -i) for i in range(1, 7))]
        if sum(value > 0 for value in history) >= 3:
            median = int(statistics.median_low(history))
            mad = int(statistics.median_low([abs(value - median) for value in history]))
            if current > median + max(3 * mad, 10000) and current * 2 > median * 3:
                facts.append(Fact(id='anomaly:' + category, kind='anomaly', title='Unusual category spending', category=category, amount_minor=current,
                    baseline_minor=median, evidence_count=6, explanation='Above the six-month lower median by more than three median absolute deviations (minimum PHP 100), and above 150% of that median.'))
    # Bounded recurrence candidates, not a subscription assertion. Text remains data.
    groups = db.execute(select(Transaction.description, Transaction.amount_minor, func.count(), func.min(Transaction.occurred_at), func.max(Transaction.occurred_at)).where(
        Transaction.user_id == user, Transaction.kind == 'expense', Transaction.occurred_at >= beginning, Transaction.occurred_at < end).group_by(
        Transaction.description, Transaction.amount_minor).having(func.count() >= 3).order_by(func.count().desc()).limit(30)).all()
    for i, (description, amount, count, first, last) in enumerate(groups):
        if last >= start and (last - first).days >= 45:
            facts.append(Fact(id=f'recurring:{i}', kind='recurring', title='Repeated expense candidate', amount_minor=amount, source_description=description, evidence_count=count,
                explanation='Same saved description and amount observed at least three times across 45+ days. Review your transaction history; this may include unrelated purchases.'))
    return InsightResult(month=month, income_minor=income, expense_minor=expense, net_minor=income - expense, facts=facts)


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=160)


@router.post('/categorize', response_model=CategorySuggestion)
def suggest_category(body: CategoryInput, db: Session = Depends(session), user=Depends(owner)):
    rate_limit(db, 'ai:' + user, settings.ai_limit)
    history = db.execute(select(Transaction.description, Transaction.category).where(Transaction.user_id == user, Transaction.kind == 'expense').order_by(Transaction.id.desc()).limit(2000)).all()
    return categorize(body.description, history)


@router.get('/insights', response_model=InsightResult)
def get_insights(month: str, db: Session = Depends(session), user=Depends(owner)):
    rate_limit(db, 'ai:' + user, settings.ai_limit)
    return insights(db, user, month)


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=500)
    month: str
    use_model: bool = False


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fact_ids: list[str] = Field(max_length=15)


async def _select_model_facts(topic, facts):
    # Never transmit raw questions, descriptions, owners, IDs or numeric amounts.
    prompt = {'task': 'Select relevant fact IDs for the supplied topic. Return JSON only.', 'topic': topic,
        'facts': [{'id': fact.id, 'kind': fact.kind} for fact in facts]}
    async with httpx.AsyncClient(timeout=settings.model_timeout_seconds, follow_redirects=False, trust_env=False) as client:
        async with client.stream('POST', settings.ollama_url + '/api/generate', json={'model': settings.ollama_model, 'prompt': json.dumps(prompt),
            'stream': False, 'format': ModelSelection.model_json_schema(), 'options': {'temperature': 0, 'num_predict': 256}}) as response:
            response.raise_for_status()
            content = b''
            async for chunk in response.aiter_bytes():
                content += chunk
                if len(content) > 16000:
                    raise ValueError('Model response too large')
            outer = json.loads(content)
            result = ModelSelection.model_validate_json(outer['response'])
            allowed = {fact.id for fact in facts}
            if any(identifier not in allowed for identifier in result.fact_ids):
                raise ValueError('Unsupported evidence')
            return [fact for fact in facts if fact.id in result.fact_ids]


async def select_model_facts(topic, facts):
    # Absolute deadline also bounds a provider that continuously drips bytes.
    async with asyncio.timeout(settings.model_timeout_seconds):
        return await _select_model_facts(topic, facts)


@router.post('/questions')
async def ask(body: QuestionInput, db: Session = Depends(session), user=Depends(owner)):
    rate_limit(db, 'ai:' + user, settings.ai_limit)
    question = body.question.lower()
    # Tools are selected from supported financial intents; inputs never become SQL.
    if re.search(r'\b(delete|drop|insert|update|password|secret|other user|another user|ignore.*instruction)\b', question):
        raise HTTPException(422, 'Ask a read-only question about your own monthly totals, budgets, changes or recurring expenses')
    topic = next((name for word, name in [('budget', 'budget'), ('recurr', 'recurring'), ('unusual', 'anomaly'), ('anomal', 'anomaly'), ('change', 'change'), ('spend', 'summary'), ('expense', 'summary'), ('income', 'summary'), ('net', 'summary'), ('summary', 'summary')] if word in question), None)
    if topic is None:
        raise HTTPException(422, 'Supported topics: monthly spending, income, net flow, budget overruns, category changes and recurring expenses')
    result = insights(db, user, body.month)
    selected = [fact for fact in result.facts if fact.kind == topic]
    engine = 'verified_read_only_tools'
    warning = None
    if body.use_model:
        consent = db.get(ModelConsent, user)
        if consent is None or not consent.enabled:
            raise HTTPException(403, 'Explicit model-processing consent is required')
        if not settings.ollama_url or not settings.ollama_model:
            raise HTTPException(503, 'No local model is configured; use verified answers without a model')
        try:
            selected = await select_model_facts(topic, selected)
            engine = 'ollama_evidence_selection'
        except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
            warning = 'Local model unavailable or invalid; verified backend answer used.'
    return {'engine': engine, 'month': body.month, 'topic': topic, 'income_minor': result.income_minor, 'expense_minor': result.expense_minor,
        'net_minor': result.net_minor, 'facts': [fact.model_dump() for fact in selected], 'warning': warning, 'limitations': result.limitations}
