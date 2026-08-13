"use client"

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

type Position = { left: number; top: number; width: number }

export function InfoTooltip({ text }: { text: string }) {
  const [isOpen, setIsOpen] = useState(false)
  const [position, setPosition] = useState<Position>({ left: 16, top: 16, width: 256 })
  const containerRef = useRef<HTMLSpanElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popupRef = useRef<HTMLSpanElement>(null)
  const tooltipId = useId()

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && isOpen) {
        setIsOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [isOpen])

  useLayoutEffect(() => {
    if (!isOpen) return
    const updatePosition = () => {
      const trigger = triggerRef.current?.getBoundingClientRect()
      const popup = popupRef.current?.getBoundingClientRect()
      if (!trigger || !popup) return
      const margin = 16
      const gap = 8
      const width = Math.min(256, window.innerWidth - margin * 2)
      const left = Math.min(
        Math.max(trigger.left + trigger.width / 2 - width / 2, margin),
        window.innerWidth - width - margin,
      )
      const above = trigger.top - popup.height - gap
      const top = above >= margin
        ? above
        : Math.min(trigger.bottom + gap, window.innerHeight - popup.height - margin)
      setPosition({ left, top: Math.max(margin, top), width })
    }
    updatePosition()
    window.addEventListener("resize", updatePosition)
    window.addEventListener("scroll", updatePosition, true)
    return () => {
      window.removeEventListener("resize", updatePosition)
      window.removeEventListener("scroll", updatePosition, true)
    }
  }, [isOpen, text])

  const popup = isOpen
    ? createPortal(
        <span
          ref={popupRef}
          id={tooltipId}
          role="tooltip"
          style={{ left: position.left, top: position.top, width: position.width }}
          className="pointer-events-none fixed z-[100] rounded-md border border-slate-700 bg-[#1e293b] p-3 text-xs font-normal leading-relaxed text-slate-200"
        >
          {text}
        </span>,
        document.body,
      )
    : null

  return (
    <span
      className="ml-1 inline-flex items-center justify-center align-middle"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => {
        if (document.activeElement !== triggerRef.current) setIsOpen(false)
      }}
      ref={containerRef}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label="More information"
        aria-expanded={isOpen}
        aria-describedby={isOpen ? tooltipId : undefined}
        onClick={() => setIsOpen(true)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        className="flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
      >
        <span className="flex h-4 w-4 items-center justify-center rounded-full border border-slate-600 bg-slate-800/50 text-[9px] font-bold text-slate-400 transition-colors hover:border-slate-400 hover:text-slate-200" aria-hidden="true">i</span>
      </button>
      {popup}
    </span>
  )
}
