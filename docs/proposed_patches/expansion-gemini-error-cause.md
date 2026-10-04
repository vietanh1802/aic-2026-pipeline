# Proposed patch (NOT applied): keep the cause when the Gemini Expand call fails

File: `backend/app/expansion.py`, `expand_query` (L182 to 251). Production code; not edited by the ablation branch.

## The problem (CONFIRMED by reading)

```python
    if (api_key) :
        try :
            raw = _call_with_retries(lambda : _gemini_expand(query_text, task_type, api_key))
            ...
        except Exception :
            pass  # falls through to the local branch
    ...
    reason = ("GEMINI_API_KEY not set" if not api_key else "Gemini unreachable") + ...
```

Every Gemini failure (an invalid key, an exhausted quota, a 429, a timeout, a response that is not JSON, an empty
answer) ends as "Gemini unreachable". The Expand button, the benchmark prefetch and anyone debugging a key all see the
same text. `scripts/check_expand.py` works around it by repeating the call once and printing the exception type and
HTTP status.

## Smallest change

Remember the last exception and put its type and, for an HTTP error, its status in the returned `error` (never the key,
which is sent in a header and is not part of the exception text):

```python
+    last_error = ""
     if (api_key) :
         try :
             ...
-        except Exception :
-            pass
+        except Exception as exc :
+            last_error = f"{type(exc).__name__} {getattr(exc, 'code', '')}".strip()
     ...
-        else "Gemini unreachable"
+        else f"Gemini failed ({last_error})"
```

The `reason` text is read by no code in this checkout (a search for "Gemini unreachable" finds only the function itself,
a comment in `scripts/check_expand.py` and a stubbed message in a test of this branch). Whether the main checkout has a
test that pins it was not checked.
