const FUTURE = [
  {
    name: "Генерация аудио",
    desc: "Озвучка закадрового текста и реплик для модулей.",
  },
  {
    name: "Генерация картинок",
    desc: "Черновые кадры, референсы локаций и реквизита.",
  },
  {
    name: "Генерация видео",
    desc: "Черновые ролики и превью сцен до съёмки.",
  },
  {
    name: "Медиабиблиотека",
    desc: "Хранение и подбор аудио, изображений и видео по проекту.",
  },
];

export function FuturePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Скоро</h1>
        <p className="mt-1 max-w-2xl text-sm text-neutral-600 dark:text-neutral-300">
          Модули за пределами текущего MVP. Пока заглушки — без рабочей логики.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {FUTURE.map((item) => (
          <div key={item.name} className="panel opacity-90">
            <p className="text-lg font-semibold">{item.name}</p>
            <p className="mt-1 text-sm text-neutral-500">{item.desc}</p>
            <p className="mt-3 text-xs uppercase tracking-wide text-neutral-400">В планах</p>
          </div>
        ))}
      </div>
    </div>
  );
}
