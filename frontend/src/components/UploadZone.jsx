import { useCallback, useRef, useState } from "react";

export default function UploadZone({ files, onFilesChange, disabled }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = useCallback(
    (list) => {
      const incoming = Array.from(list).filter((f) =>
        f.name.toLowerCase().endsWith(".pdf")
      );
      if (!incoming.length) return;
      const byKey = new Map(files.map((f) => [f.name + f.size, f]));
      incoming.forEach((f) => byKey.set(f.name + f.size, f));
      onFilesChange(Array.from(byKey.values()));
    },
    [files, onFilesChange]
  );

  const removeFile = (key) => {
    onFilesChange(files.filter((f) => f.name + f.size !== key));
  };

  return (
    <div className="upload-block">
      <div
        className={`dropzone ${dragOver ? "dropzone--over" : ""} ${
          disabled ? "dropzone--disabled" : ""
        }`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (!disabled) addFiles(e.dataTransfer.files);
        }}
      >
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="dropzone__title">Przeciągnij faktury PDF tutaj</p>
        <p className="dropzone__hint">albo kliknij, aby wybrać pliki z dysku</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          hidden
          disabled={disabled}
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="file-chip-list">
          {files.map((f) => {
            const key = f.name + f.size;
            return (
              <li className="file-chip" key={key}>
                <span className="file-chip__name" title={f.name}>
                  {f.name}
                </span>
                <span className="file-chip__size">
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                <button
                  type="button"
                  className="file-chip__remove"
                  aria-label={`Usuń ${f.name}`}
                  disabled={disabled}
                  onClick={() => removeFile(key)}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
