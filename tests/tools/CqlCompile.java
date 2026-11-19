import java.io.File;
import java.nio.file.Path;
import org.cqframework.cql.cql2elm.CqlCompilerException;
import org.cqframework.cql.cql2elm.CqlTranslator;
import org.cqframework.cql.cql2elm.DefaultLibrarySourceProvider;
import org.cqframework.cql.cql2elm.LibraryManager;
import org.cqframework.cql.cql2elm.ModelManager;
import org.cqframework.cql.cql2elm.quick.FhirLibrarySourceProvider;

/**
 * Translate CQL files with cql-to-elm and report errors (single-file Java program).
 *
 * <p>Usage: {@code java -cp <cql-to-elm classpath> CqlCompile.java <include dir> <file.cql>...}
 *
 * <p>Includes resolve from {@code <include dir>} ({@code <name>-<version>.cql}) and FHIRHelpers
 * from the bundled FHIR library provider. Exit code 1 when any file has an error. Used by
 * tests/test_cql_initial_expression.py; see fix/20260929-cql-initial-expression-on-device.md.
 */
public class CqlCompile {
  public static void main(String[] args) throws Exception {
    LibraryManager libraryManager = new LibraryManager(new ModelManager());
    libraryManager.getLibrarySourceLoader().registerProvider(new FhirLibrarySourceProvider());
    libraryManager.getLibrarySourceLoader().registerProvider(new DefaultLibrarySourceProvider(Path.of(args[0])));
    boolean failed = false;
    for (int i = 1; i < args.length; i++) {
      CqlTranslator translator = CqlTranslator.fromFile(new File(args[i]), libraryManager);
      System.out.println("== " + args[i] + ": " + translator.getErrors().size() + " error(s)");
      for (CqlCompilerException error : translator.getErrors()) {
        String line = error.getLocator() == null ? "" : error.getLocator().getStartLine() + ": ";
        System.out.println("  " + line + error.getMessage());
      }
      failed |= !translator.getErrors().isEmpty();
    }
    System.exit(failed ? 1 : 0);
  }
}
