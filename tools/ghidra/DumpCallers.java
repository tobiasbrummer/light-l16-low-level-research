// SPDX-License-Identifier: MIT
// Print direct callers of named functions or exact addresses.
// Usage: -postScript DumpCallers.java <function-name|@address> [...]
//
// For ELF imports, Ghidra commonly creates a local PLT thunk next to the
// EXTERNAL symbol. Only the thunk may own the code references; use @address to
// select that local function explicitly.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpCallers extends GhidraScript {

    private Set<Function> resolve(String target) {
        Set<Function> matches = new LinkedHashSet<>();
        if (target.startsWith("@")) {
            String raw = target.substring(1).replaceFirst("^0[xX]", "");
            Address address = toAddr(Long.parseUnsignedLong(raw, 16));
            Function function = getFunctionAt(address);
            if (function == null) function = getFunctionContaining(address);
            if (function != null) matches.add(function);
            return matches;
        }

        FunctionIterator functions =
                currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext()) {
            Function function = functions.next();
            if (target.equals(function.getName()) ||
                    target.equals(function.getName(true))) {
                matches.add(function);
            }
        }
        return matches;
    }

    public void run() throws Exception {
        for (String target : getScriptArgs()) {
            Set<Function> matches = resolve(target);
            println("### TARGET " + target + ": " + matches.size() + " matches");
            for (Function callee : matches) {
                println("### FUNCTION " + callee.getName(true) + " @" +
                        callee.getEntryPoint() +
                        (callee.isThunk() ? " THUNK" : ""));
                ReferenceIterator references = currentProgram.getReferenceManager()
                        .getReferencesTo(callee.getEntryPoint());
                int count = 0;
                while (references.hasNext()) {
                    Reference reference = references.next();
                    Address source = reference.getFromAddress();
                    Function caller = getFunctionContaining(source);
                    String owner = caller == null
                            ? "<no function>"
                            : caller.getName(true) + " @" + caller.getEntryPoint();
                    println(source + "  " + reference.getReferenceType() +
                            "  " + owner);
                    count++;
                }
                println("### CALLERS " + count);
            }
        }
    }
}
