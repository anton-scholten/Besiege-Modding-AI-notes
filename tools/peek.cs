// Reads Besiege's own assemblies with the Mono.Cecil that ships in
// Besiege_Data/Managed. Every API claim in these notes was checked with this.
//
//   ./tools/peek.sh types <substring> [assembly...]   types whose name matches
//   ./tools/peek.sh sig   <Type>                      fields, props, methods
//   ./tools/peek.sh dump  <Type>                      the same, plus every IL body
//   ./tools/peek.sh member <substring>                who declares a member of that name
//   ./tools/peek.sh calls <substring>                 who references that member
//   ./tools/peek.sh str   <substring>                 who loads a string containing it
//   ./tools/peek.sh check <file>                      one "Type" or "Type::Member" per
//                                                     line -> ok / MISSING
//
// `check` is the one that matters for these notes: keep a list of every API a
// document claims, and re-run it against a new Besiege before trusting the document.
using System;
using System.Collections.Generic;
using System.IO;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class Peek
{
    static void Collect(TypeDefinition t, List<TypeDefinition> into)
    {
        into.Add(t);
        foreach (TypeDefinition n in t.NestedTypes) Collect(n, into);
    }

    static List<TypeDefinition> All(string[] assemblies)
    {
        List<TypeDefinition> all = new List<TypeDefinition>();
        foreach (string asm in assemblies)
            foreach (ModuleDefinition m in AssemblyDefinition.ReadAssembly(asm).Modules)
                foreach (TypeDefinition t in m.Types) Collect(t, all);
        return all;
    }

    public static int Main(string[] args)
    {
        string mode = args[0], what = args[1];
        string[] asms = new string[args.Length - 2];
        Array.Copy(args, 2, asms, 0, asms.Length);
        List<TypeDefinition> all = All(asms);

        if (mode == "types")
        {
            foreach (TypeDefinition t in all)
                if (what == "*" || t.FullName.ToLower().Contains(what.ToLower()))
                    Console.WriteLine(t.FullName);
            return 0;
        }

        if (mode == "sig" || mode == "dump")
        {
            foreach (TypeDefinition t in all)
            {
                if (t.FullName != what && t.Name != what) continue;
                Console.WriteLine("type " + t.FullName + " : " +
                                  (t.BaseType == null ? "" : t.BaseType.FullName));
                foreach (var i in t.Interfaces) Console.WriteLine("  impl " + i.FullName);
                foreach (FieldDefinition f in t.Fields)
                    Console.WriteLine("  field " + (f.IsPublic ? "public " : "private ") +
                                      (f.IsStatic ? "static " : "") + f.FieldType.Name + " " + f.Name);
                foreach (PropertyDefinition p in t.Properties)
                    Console.WriteLine("  prop  " + p.PropertyType.Name + " " + p.Name);
                foreach (MethodDefinition m in t.Methods)
                {
                    Console.WriteLine("  method " + (m.IsPublic ? "public " : "private ") +
                                      (m.IsStatic ? "static " : "") + m.ReturnType.Name + " " +
                                      m.Name + "(" + m.Parameters.Count + ")");
                    if (mode == "dump" && m.HasBody)
                        foreach (Instruction i in m.Body.Instructions)
                            Console.WriteLine("      " + i);
                }
            }
            return 0;
        }

        if (mode == "member")
        {
            foreach (TypeDefinition t in all)
            {
                foreach (FieldDefinition f in t.Fields)
                    if (f.Name.Contains(what)) Console.WriteLine("field  " + t.FullName + "::" + f.Name);
                foreach (PropertyDefinition p in t.Properties)
                    if (p.Name.Contains(what)) Console.WriteLine("prop   " + t.FullName + "::" + p.Name);
                foreach (MethodDefinition m in t.Methods)
                    if (m.Name.Contains(what)) Console.WriteLine("method " + t.FullName + "::" + m.Name);
            }
            return 0;
        }

        if (mode == "calls")
        {
            foreach (TypeDefinition t in all)
                foreach (MethodDefinition m in t.Methods)
                {
                    if (!m.HasBody) continue;
                    foreach (Instruction i in m.Body.Instructions)
                    {
                        MemberReference r = i.Operand as MemberReference;
                        if (r != null && r.FullName.Contains(what))
                            Console.WriteLine(t.FullName + "::" + m.Name + " -> " + r.FullName);
                    }
                }
            return 0;
        }

        if (mode == "str")
        {
            foreach (TypeDefinition t in all)
                foreach (MethodDefinition m in t.Methods)
                {
                    if (!m.HasBody) continue;
                    foreach (Instruction i in m.Body.Instructions)
                        if (i.OpCode == OpCodes.Ldstr && i.Operand is string &&
                            ((string)i.Operand).ToLower().Contains(what.ToLower()))
                            Console.WriteLine(t.FullName + "::" + m.Name + "  \"" + i.Operand + "\"");
                }
            return 0;
        }

        if (mode == "check")
        {
            Dictionary<string, TypeDefinition> byName = new Dictionary<string, TypeDefinition>();
            foreach (TypeDefinition t in all)
            {
                byName[t.FullName] = t;
                if (!byName.ContainsKey(t.Name)) byName[t.Name] = t;
            }
            int bad = 0;
            foreach (string raw in File.ReadAllLines(what))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                string type = line, member = null;
                int at = line.IndexOf("::");
                if (at >= 0) { type = line.Substring(0, at); member = line.Substring(at + 2); }
                TypeDefinition t;
                if (!byName.TryGetValue(type, out t))
                { Console.WriteLine("MISSING TYPE   " + line); bad++; continue; }
                if (member == null) { Console.WriteLine("ok             " + line); continue; }
                bool found = false;
                foreach (FieldDefinition f in t.Fields) if (f.Name == member) found = true;
                foreach (PropertyDefinition p in t.Properties) if (p.Name == member) found = true;
                foreach (MethodDefinition m in t.Methods) if (m.Name == member) found = true;
                foreach (EventDefinition e in t.Events) if (e.Name == member) found = true;
                foreach (TypeDefinition n in t.NestedTypes) if (n.Name == member) found = true;
                Console.WriteLine((found ? "ok             " : "MISSING MEMBER ") + line);
                if (!found) bad++;
            }
            Console.WriteLine("--- " + bad + " problem(s)");
            return bad == 0 ? 0 : 1;
        }

        Console.WriteLine("modes: types sig dump member calls str check");
        return 1;
    }
}
