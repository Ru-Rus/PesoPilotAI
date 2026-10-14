"""Reproducible synthetic classifier evaluation; not a production-quality claim."""
import json
from app.intelligence import categorize

training = [
    ('coffee cafe espresso', 'Food & dining'), ('restaurant lunch dinner', 'Food & dining'),
    ('bus train fare', 'Transport'), ('taxi jeep transport', 'Transport'),
    ('pharmacy medicine doctor', 'Health'), ('hospital clinic medicine', 'Health'),
    ('electric water utility', 'Bills'), ('internet phone bill', 'Bills'),
]
gold = [
    ('coffee espresso', 'Food & dining'), ('restaurant dinner', 'Food & dining'), ('cafe lunch', 'Food & dining'),
    ('bus fare', 'Transport'), ('train fare', 'Transport'), ('taxi transport', 'Transport'),
    ('pharmacy medicine', 'Health'), ('doctor hospital', 'Health'), ('clinic medicine', 'Health'),
    ('electric utility', 'Bills'), ('water utility', 'Bills'), ('internet bill', 'Bills'),
]
predictions = [categorize(text, training).category for text, _ in gold]
correct = sum(prediction == expected for prediction, (_, expected) in zip(predictions, gold))
unknown = categorize('previously unseen merchant', training)
assert correct / len(gold) >= 0.9
assert unknown.category is None
print(json.dumps({'correct': correct, 'cases': len(gold), 'accuracy': correct / len(gold), 'unknown_abstained': unknown.category is None,
    'scope': 'fixed synthetic holdout phrases; no real-world accuracy or hosted-model quality claim'}))
