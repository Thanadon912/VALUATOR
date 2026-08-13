"use client";

export function ValuationSkeleton() {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {[1, 2, 3, 4, 5].map((i) => (
        <div 
          key={i} 
          className="flex h-[400px] flex-col animate-pulse rounded-md border border-[#1A2E20] bg-[#111613]/80 p-6 motion-reduce:animate-none"
        >
          <div className="h-6 w-1/3 bg-[#1A2E20] rounded mb-6"></div>
          
          <div className="flex justify-between mb-8">
            <div className="h-10 w-1/4 bg-[#1A2E20] rounded"></div>
            <div className="h-10 w-1/4 bg-[#1A2E20] rounded"></div>
          </div>
          
          <div className="flex-1 bg-[#1A2E20]/50 rounded-lg"></div>
        </div>
      ))}
    </div>
  );
}
