function describe(dup, skipped) {
  const target = skipped ? "pominięto" : "wygląda jak duplikat";
  if (dup.reason === "identical_file") {
    return (
      <>
        <strong>{dup.plik}</strong> to dokładnie ten sam plik co{" "}
        <strong>{dup.matches_plik}</strong> — {target}.
      </>
    );
  }
  return (
    <>
      <strong>{dup.plik}</strong> to prawdopodobnie ta sama faktura co{" "}
      <strong>{dup.matches_plik}</strong> (nr {dup.numer_faktury || "—"}, {dup.sprzedawca || "—"}) —{" "}
      {target}.
    </>
  );
}

export default function DuplicateWarning({ duplicates, skipped }) {
  if (!duplicates || !duplicates.length) return null;
  return (
    <div className="alert alert--warning">
      <strong>
        {skipped
          ? `Pominięto ${duplicates.length} ${duplicates.length === 1 ? "duplikat" : "duplikaty"}:`
          : `Wygląda na to, że wgrano ${duplicates.length} ${
              duplicates.length === 1 ? "duplikat" : "duplikaty"
            }:`}
      </strong>
      <ul>
        {duplicates.map((d, i) => (
          <li key={i}>{describe(d, skipped)}</li>
        ))}
      </ul>
    </div>
  );
}
