// Injection key for opening an item in the drill-in dialog. Provided by
// DrillInArrayField, injected by ObjectArrayField lists shown in "summary"
// mode at any depth below it. The value is (path, label, fields) => void.
export const DRILL_INTO = Symbol("drillInto");
