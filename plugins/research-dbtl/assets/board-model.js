// Whole-cycle folding never changes task status or evidence.
function groupCycles(tasks) {
  const groups = new Map();
  for (const task of tasks) {
    if (!groups.has(task.cycle)) groups.set(task.cycle, []);
    groups.get(task.cycle).push(task);
  }
  return [...groups].map(([cycle, tasks]) => ({cycle, tasks,
    completed: tasks.length > 0 && tasks.every(task => task.status === 'done' && !task.stale)}));
}
