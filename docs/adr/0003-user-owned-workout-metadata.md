# User-owned workout metadata

Performed reps, load value/unit, and notes are optional fields on the user-owned video record. The earlier coaching names (weight, corrected reps, and notes) remain accepted as compatibility aliases and are retained for existing rows. All supplied metadata is saved atomically with the save transition so the saved library and future coaching history share one source of truth.
