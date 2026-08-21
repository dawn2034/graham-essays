# Code and Links

Long web addresses must wrap safely in both formats: <https://paulgraham.com/articles.html>. Inline code such as `result = model(prompt)` should remain legible but visually secondary to the prose.

```python
def answer(question: str) -> str:
    return question.strip()
```

A deliberately long identifier tests emergency line breaking:

```python
this_is_a_deliberately_long_identifier_for_layout_testing = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
```
