import { Hono } from "hono"
import { createRoutes } from "./routes.js"

const app = new Hono()
createRoutes(app, { eventStore: null })

export default app
