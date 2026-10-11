/* Saving a visit requests local writing once; reading it never runs inference. */
(function (root) {
  "use strict";
  function create({ api, runJob }) {
    const pending = new Map();
    function prepare(visit, current = () => true, retry = false) {
      const key = visit.id + ":" + visit.revision;
      if (pending.has(key)) return pending.get(key);
      const task = (async () => {
        const job = await api(`/experiences/${visit.id}/prepare`, {
          method: "POST",
          body: { source_revision: visit.revision, retry },
        });
        let result = await runJob(job, (result) => result, current);
        if (!result) {
          const completed = await api(`/jobs/${job.id}`);
          if (completed.status !== "complete")
            throw Error(
              completed.message ||
                "AI preparation did not finish. Your experience is saved.",
            );
          result = completed.result;
        }
        return result;
      })();
      pending.set(key, task);
      task.finally(() => pending.delete(key)).catch(() => {});
      return task;
    }
    return { prepare };
  }
  root.NukkadVisitMemory = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadVisitMemory;
})(globalThis);
