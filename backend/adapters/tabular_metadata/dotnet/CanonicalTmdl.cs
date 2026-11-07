using Microsoft.AnalysisServices.Tabular;

// Canonical TMDL is what Power BI Desktop writes: Microsoft's TMDL serializer
// output with CRLF line endings. The serializer itself uses Environment.NewLine,
// so on Linux and macOS it writes LF. Every bridge command that serializes TMDL
// goes through here, so the canonical check, the model writer and the read
// adapter give the same bytes on every OS.
static class CanonicalTmdl
{
    public static void SerializeToFolder(Database database, string folder)
    {
        TmdlSerializer.SerializeDatabaseToFolder(database, folder);
        if (Environment.NewLine == "\r\n") return;
        foreach (var file in Directory.GetFiles(folder, "*.tmdl", SearchOption.AllDirectories))
            File.WriteAllBytes(file, ToCrlf(File.ReadAllBytes(file)));
    }

    // Turns every LF that is not already part of a CRLF into CRLF. Other bytes
    // are kept exactly.
    public static byte[] ToCrlf(byte[] data)
    {
        var result = new List<byte>(data.Length + data.Length / 16);
        for (var i = 0; i < data.Length; i++)
        {
            if (data[i] == (byte)'\n' && (i == 0 || data[i - 1] != (byte)'\r')) result.Add((byte)'\r');
            result.Add(data[i]);
        }
        return result.ToArray();
    }
}
