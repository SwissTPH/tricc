import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.hl7.fhir.r4.context.SimpleWorkerContext;
import org.hl7.fhir.r4.formats.IParser;
import org.hl7.fhir.r4.formats.JsonParser;
import org.hl7.fhir.r4.model.StructureMap;
import org.hl7.fhir.r4.utils.StructureMapUtilities;

/**
 * Compile FHIR Mapping Language (.map) to a StructureMap JSON resource.
 *
 * <p>Uses the same {@link StructureMapUtilities#parse} OpenSRP / HAPI uses. Does not transform
 * data — only FML → {@code group[]}.
 *
 * <p>Usage: {@code java CompileStructureMap <file.map> [out.json]}
 */
public final class CompileStructureMap {
  public static void main(String[] args) throws Exception {
    if (args.length < 1 || "-h".equals(args[0]) || "--help".equals(args[0])) {
      System.err.println("Usage: CompileStructureMap <file.map> [out.json]");
      System.exit(args.length < 1 ? 2 : 0);
    }
    Path mapPath = Path.of(args[0]);
    String fml = Files.readString(mapPath, StandardCharsets.UTF_8);
    String srcName = mapPath.getFileName().toString();
    StructureMapUtilities utils = new StructureMapUtilities(SimpleWorkerContext.fromNothing());
    StructureMap sm = utils.parse(fml, srcName);
    if (sm.getGroup() == null || sm.getGroup().isEmpty()) {
      throw new IllegalStateException("HAPI parse produced 0 groups from " + mapPath);
    }
    String json =
        new JsonParser()
            .setOutputStyle(IParser.OutputStyle.PRETTY)
            .composeString(sm);
    if (args.length >= 2) {
      Files.writeString(Path.of(args[1]), json + "\n", StandardCharsets.UTF_8);
    } else {
      System.out.print(json);
      if (!json.endsWith("\n")) {
        System.out.println();
      }
    }
    System.err.println(
        "compiled "
            + srcName
            + " groups="
            + sm.getGroup().size()
            + " topRules="
            + sm.getGroupFirstRep().getRule().size());
  }

  private CompileStructureMap() {}
}
