FROM node:20-alpine AS build

# Set the working directory inside the container
WORKDIR /app

# Copy the package.json and package-lock.json (if available) first to leverage Docker cache for npm install
COPY package*.json ./

# Install dependencies (only production dependencies)
RUN npm install --frozen-lockfile

# Copy the rest of the application code to the container
COPY . .

# Build the Vite project for production
RUN npm run build

# Step 2: Production Stage
# Use a lightweight image for serving the built app (Alpine Linux + Nginx)
FROM nginx:alpine AS production

# Copy the built files from the build stage to the appropriate Nginx directory
COPY --from=build /app/build /usr/share/nginx/html

# Copy a custom Nginx configuration file
COPY nginx.conf /etc/nginx/conf.d/default.conf


# Expose the port the app will run on
EXPOSE 80

# Command to run Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
