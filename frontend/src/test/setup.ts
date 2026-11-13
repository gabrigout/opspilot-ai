import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom does not implement layout APIs used by the chat auto-scroll.
Element.prototype.scrollIntoView = () => {}

afterEach(() => cleanup())
