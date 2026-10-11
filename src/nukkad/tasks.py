"""Bounded inference with traceable, content-free attempt diagnostics."""

import time

from nukkad.ollama import ModelFailure


def run_task(model, response_type, prompt, deadline, validator, schema=None, *, task, version=1):
    attempts, correction = [], ""
    model_tag = getattr(getattr(model, "config", None), "model", None)
    for attempt in range(2):
        began = time.monotonic()
        metrics = {}
        try:
            value, metrics = model.generate(response_type, prompt + correction, deadline, schema)
            validator(value)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "elapsed_seconds": round(time.monotonic() - began, 3),
                    "status": "accepted",
                    "metrics": metrics,
                }
            )
            return value, {
                **metrics,
                "model_tag": model_tag,
                "task": task,
                "prompt_version": version,
                "attempts": attempts,
            }
        except (ModelFailure, ValueError) as error:
            category = error.category if isinstance(error, ModelFailure) else "domain_validation"
            rule = (
                "layout"
                if "lines" in str(error)
                else "membership"
                if "IDs" in str(error) or "evidence" in str(error)
                else "explanation_style"
                if "explanation" in str(error)
                else "unsupported_claim"
                if "claim" in str(error) or "feature" in str(error)
                else "validation"
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "elapsed_seconds": round(time.monotonic() - began, 3),
                    "status": "rejected",
                    "category": category,
                    "validation_rule": rule,
                    "validation_message": str(error),
                    "metrics": error.diagnostics if isinstance(error, ModelFailure) else metrics,
                }
            )
            correction = (
                "\nPrevious response was rejected: "
                + str(error)
                + ". Correct only the rejected fields."
            )
            if time.monotonic() >= deadline:
                break
    raise ModelFailure(
        "Local model output failed validation after the bounded corrective retry",
        category,
        {"model_tag": model_tag, "task": task, "prompt_version": version, "attempts": attempts},
    )
