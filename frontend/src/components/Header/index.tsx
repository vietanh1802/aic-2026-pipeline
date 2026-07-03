export default function Header() {
  return (
    <div className="font-baloo text-xl flex flex-row justify-between mx-8 my-9 items-center">
      <div className="flex flex-row space-x-2 justify-center items-center hover:cursor-pointer">
        <img src="/logo.svg" height={48} width={48} />
        <div className="font-bold">Scavenger</div>
      </div>
      <div className="hover:cursor-pointer">
        <span className="font-bold">VQF</span> - Video Query Finder
      </div>
    </div>
  );
}
