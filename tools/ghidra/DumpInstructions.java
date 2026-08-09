// SPDX-License-Identifier: MIT
// Print instructions starting at a named function.
// Usage: -postScript DumpInstructions.java <function-name> [<count> [<offset>]]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;

public class DumpInstructions extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("### missing function name");
            return;
        }
        int maximum = args.length > 1 ? Integer.parseInt(args[1]) : 96;
        long offset = args.length > 2 ? Long.decode(args[2]) : 0;
        Function target = null;
        FunctionIterator functions =
                currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext()) {
            Function function = functions.next();
            if (args[0].equals(function.getName()) ||
                    args[0].equals(function.getName(true))) {
                target = function;
                break;
            }
        }
        if (target == null) {
            println("### no function: " + args[0]);
            return;
        }

        Address start = target.getEntryPoint().add(offset);
        println("### INSTRUCTIONS " + target.getName(true) + " @" + start);
        if (getInstructionAt(start) == null) {
            disassemble(start);
        }
        Instruction instruction = getInstructionAt(start);
        for (int count = 0; instruction != null && count < maximum; count++) {
            println(instruction.getAddress() + "  " + instruction);
            instruction = instruction.getNext();
        }
    }
}
