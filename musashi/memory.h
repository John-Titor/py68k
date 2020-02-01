/*
 * Memory API for Musashi 4.x
 */

typedef enum {
    MEM_READ = 'R',
    MEM_WRITE = 'W',
    INVALID_READ = 'r',
    INVALID_WRITE = 'w',
} mem_operation_t;

typedef enum {
    MEM_WIDTH_8,
    MEM_WIDTH_16,
    MEM_WIDTH_32
} mem_width_t;

typedef uint32_t (*mem_device_handler_t)(mem_operation_t operation, 
                                         uint32_t address, 
                                         mem_width_t width,
                                         uint32_t value);

typedef void (*mem_trace_handler_t)(mem_operation_t operation,
                                    uint32_t address,
                                    mem_width_t width,
                                    uint32_t value);

bool mem_add_memory(uint32_t base, uint32_t size, bool writable, const void *with_bytes);
bool mem_add_device(uint32_t base, uint32_t size);

void mem_set_device_handler(mem_device_handler_t handler);
void mem_set_trace_handler(mem_trace_handler_t handler);
void mem_enable_tracing(bool enable);
void mem_enable_bus_error(bool enable); 

uint32_t mem_read_memory(uint32_t address, mem_width_t width);
void mem_write_memory(uint32_t address, mem_width_t width, uint32_t value);
void mem_write_bulk(uint32_t address, uint8_t *buffer, uint32_t size);
