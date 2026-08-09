// SPDX-License-Identifier: MIT
// Decompile named functions or exact addresses from the current program.
// Usage: -postScript DumpFunctions.java <function-name|@address> [...]
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpFunctions extends GhidraScript {

    private void decompile(DecompInterface decompiler, Function function) {
        println("### FUNCTION " + function.getName(true) + " @" +
                function.getEntryPoint() + " (" +
                function.getBody().getNumAddresses() + " bytes)");
        DecompileResults result = decompiler.decompileFunction(function, 300, monitor);
        if (result.decompileCompleted()) {
            println(result.getDecompiledFunction().getC());
        }
        else {
            println("// Decompilation failed: " + result.getErrorMessage());
        }
    }

    public void run() throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        Set<Function> done = new LinkedHashSet<>();

        for (String target : getScriptArgs()) {
            Set<Function> matches = new LinkedHashSet<>();
            if (target.startsWith("@")) {
                String raw = target.substring(1).replaceFirst("^0[xX]", "");
                Address address = toAddr(Long.parseUnsignedLong(raw, 16));
                Function function = getFunctionContaining(address);
                if (function == null) function = getFunctionAt(address);
                if (function != null) matches.add(function);
            }
            else {
                FunctionIterator functions =
                        currentProgram.getFunctionManager().getFunctions(true);
                while (functions.hasNext()) {
                    Function function = functions.next();
                    if (target.equals(function.getName()) ||
                            target.equals(function.getName(true))) {
                        matches.add(function);
                    }
                }
            }

            println("### TARGET " + target + ": " + matches.size() + " matches");
            for (Function function : matches) {
                if (done.add(function)) decompile(decompiler, function);
            }
        }
        decompiler.dispose();
    }
}
