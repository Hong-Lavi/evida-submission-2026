"""Check whether a quoted sentence supports the clause it was attached to.

The anchor check already proves a quote is present in the stored row. That catches a fabricated
quote but not an unrelated one: a clause can cite a real sentence that says nothing about it.

The clauses this product writes are Korean and the sources are English, so the check has to work
across languages. An English-only fact checker was tried first and returned "unsupported" for
every Korean clause regardless of content, which is worse than no check; this uses a multilingual
NLI model instead.

What this is not: not a judgement about whether the clause is true, and not a review of the
science. It answers one narrow question - does this sentence, on its own, entail this statement -
and the verdict is recorded beside the model's unchanged record, never in place of it.
"""
import json
import sys

MODEL = 'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7'
MAX_INPUT_TOKENS = 512
# An NLI label is not a verdict about the world. "neutral" means this sentence does not carry the
# claim, which is different from the claim being wrong; "contradiction" is the one that matters.
STATUS = {'entailment': 'supported', 'neutral': 'not_carried', 'contradiction': 'contradicted'}


def load(device):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL)
    model.eval().to(device)
    return tokenizer, model, torch


def verdict(tokenizer, model, torch, device, document, claim):
    encoded = tokenizer(document, claim, return_tensors='pt', truncation=True,
                        max_length=MAX_INPUT_TOKENS).to(device)
    truncated = int(encoded['input_ids'].shape[-1]) >= MAX_INPUT_TOKENS
    with torch.no_grad():
        scores = torch.softmax(model(**encoded).logits[0], -1)
    labels = {model.config.id2label[i].lower(): float(scores[i]) for i in range(len(scores))}
    best = max(labels, key=labels.get)
    return {'status': STATUS.get(best, best), 'label': best,
            'confidence': round(labels[best], 3),
            'scores': {k: round(v, 3) for k, v in labels.items()},
            'input_truncated': truncated}


def main(request_path):
    request = json.loads(open(request_path, encoding='utf-8').read())
    device = request.get('device', 'cuda')
    try:
        tokenizer, model, torch = load(device)
    except Exception as error:
        json.dump({'status': 'unavailable', 'reason': f'{type(error).__name__}: {error}',
                   'results': []}, open(request['out'], 'w', encoding='utf-8'), ensure_ascii=False)
        return
    results = []
    for pair in request['pairs']:
        try:
            value = verdict(tokenizer, model, torch, device, pair['document'], pair['claim'])
        except Exception as error:
            value = {'status': 'failed', 'reason': f'{type(error).__name__}: {error}'}
        results.append({'id': pair.get('id'), **value})
    with open(request['out'], 'w', encoding='utf-8') as handle:
        json.dump({'status': 'succeeded', 'model': MODEL, 'results': results,
                   'meaning': 'Whether the quoted sentence alone entails the stated clause, across '
                              'languages. not_carried means this sentence does not carry the claim, '
                              'not that the claim is wrong. contradicted means the sentence says '
                              'the opposite and is worth a look. Advisory only.'},
                  handle, ensure_ascii=False)


if __name__ == '__main__':
    main(sys.argv[1])
