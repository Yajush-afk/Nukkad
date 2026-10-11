"""Bounded inference with traceable, content-free attempt diagnostics."""

import time

from nukkad.ollama import ModelFailure


def run_task(model, response_type, prompt, deadline, validator, schema=None, *, task, version=1):
    attempts, correction = [], ""
    model_tag = getattr(getattr(model, "config", None), "model", None)
    for attempt in range(2):
        began = time.monotonic()
        metrics, value = {}, None
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
                    "validation_message": str(error)
                    if not isinstance(error, ModelFailure)
                    and str(error)
                    in {
                        "Each passage needs an exact nonempty source quote",
                        "Write about the person's reported visit, not a generic scene caption",
                        "Retain the reported positive experience in the narrative",
                        "Retain the reported discovery about previous awareness",
                        "Write the journal in third person",
                        "Do not add emotions absent from the supporting quote",
                        "Do not turn negative experience into enjoyment",
                        "Do not add achievements or encounters absent from the quote",
                        "Do not add names absent from the source passage",
                        "Do not add unsupported dates, counts or measurements",
                        "A not-taken outcome cannot become a completed outing",
                        "Keep the journal within its editable text limit",
                        "Write only the visit narrative; remove placeholders and editorial comments",
                        "Include the full supporting sentence for every negative, skipped or uncertain report",
                    }
                    else None,
                    "metrics": error.diagnostics if isinstance(error, ModelFailure) else metrics,
                }
            )
            previous = value.model_dump_json() if value is not None else ""
            correction = (
                (
                    "\nPrevious structured response to repair: " + previous
                    if len(previous) <= 1800
                    else ""
                )
                + "\nPrevious response was rejected: "
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
