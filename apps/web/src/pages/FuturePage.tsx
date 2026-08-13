const FUTURE = [
  "Media Library",
  "360 Video Upload",
  "Video Annotation",
  "AI Image Generation",
  "AI Video Generation",
  "Tablet Export Package",
  "Client Approval Portal",
  "Runtime Player",
  "Eye-tracking Integration",
];

export function FuturePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-4xl">Coming soon</h1>
        <p className="mt-1 text-ink-600 dark:text-ink-300">
          Зафиксированные placeholders за пределами MVP.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {FUTURE.map((name) => (
          <div key={name} className="panel opacity-80">
            <p className="font-display text-lg">{name}</p>
            <p className="text-sm text-ink-500">Future module</p>
          </div>
        ))}
      </div>
    </div>
  );
}
