export default function Header() {
  return (
    <div className="font-baloo text-xl flex flex-row justify-between mx-8 my-9 items-center">
      <div className="flex flex-row space-x-2 justify-center items-center hover:cursor-pointer">
        <img src="/logo.svg" height={48} width={48} />
        <div className="font-bold">Scavenger</div>
      </div>
      <div className="flex flex-row items-center gap-x-3">
        <div className="hover:cursor-pointer">
          <span className="font-bold">VQF</span> - Video Query Finder
        </div>
        <span
          className="text-xs font-medium text-neutral-500 border border-neutral-300 rounded-[4px] px-2 py-0.5"
          title={`Build ${__APP_VERSION__} · commit ${__APP_COMMIT__}`}
        >
          v{__APP_VERSION__}
          <span className="text-neutral-400"> · {__APP_COMMIT__}</span>
        </span>
      </div>
    </div>
  );
}
