// SPDX-License-Identifier: MIT
// Print references to a named symbol and the containing functions.
// Usage: -postScript DumpReferences.java <symbol-name>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class DumpReferences extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            println("### exactly one symbol name is required");
            return;
        }

        SymbolIterator symbols = currentProgram.getSymbolTable().getSymbols(args[0]);
        boolean found = false;
        while (symbols.hasNext()) {
            found = true;
            Symbol symbol = symbols.next();
            Address target = symbol.getAddress();
            println("### SYMBOL " + symbol.getName(true) + " @" + target);
            ReferenceIterator references = currentProgram.getReferenceManager()
                    .getReferencesTo(target);
            int count = 0;
            while (references.hasNext()) {
                Reference reference = references.next();
                Address source = reference.getFromAddress();
                Function function = getFunctionContaining(source);
                String owner = function == null
                        ? "<no function>"
                        : function.getName(true) + " @" + function.getEntryPoint();
                println(source + "  " + reference.getReferenceType() + "  " + owner);
                count++;
            }
            println("### REFERENCES " + count);
        }
        if (!found) {
            println("### no symbol: " + args[0]);
        }
    }
}
